import type { EngineInterface, Register, SessionRateLimit } from 'claude-code'

// Write the usage limits (rate limits) to /tmp/claude-<uid>/rate-limits.json.
// An external script that watches the remaining weekly quota reads it. Format:
// {"five_hour": {"used_percentage": 17, "resets_at": 1791553800, "seen_at": 1791552278},
//  "seven_day": {"used_percentage": 75, "resets_at": 1791615600, "seen_at": 1791552278,
//                "burn_rate": 0.499, "projected_surplus": 14.5, "stage": "none"}}
// seven_day also carries a projection computed as of its seen_at (see project()).

const KINDS = ['five_hour', 'seven_day'] as const
type Kind = (typeof KINDS)[number]
type Window = { used_percentage: number; resets_at: number; seen_at: number }
type Snapshot = Partial<Record<Kind, Window>>

const isWindow = (v: unknown): v is Window => {
  const w = v as Window | null
  return (
    typeof w === 'object' &&
    w !== null &&
    Number.isFinite(w.used_percentage) &&
    Number.isFinite(w.resets_at) &&
    Number.isFinite(w.seen_at)
  )
}

// A newer window (larger resets_at) wins; within the same window the higher usage wins. Usage never drops until the reset.
// This rule keeps stale values from parallel sessions from overwriting newer ones.
const isNewer = (next: Window, prev: Window | undefined): boolean =>
  prev === undefined ||
  next.resets_at > prev.resets_at ||
  (next.resets_at === prev.resets_at && next.used_percentage > prev.used_percentage)

// Weekly surplus projection, as of the window's seen_at:
//   hours_left        = (resets_at - seen_at) / 3600
//   burn_rate         = used / hours elapsed this week (%/hour); the weekly average 100/168 while under 1 hour has passed
//   projected_surplus = (100 - used) - hours_left * burn_rate * RESERVE   (percentage points left at the reset)
//   stage             = 'high' at SURPLUS_HIGH or more, 'low' at SURPLUS_LOW or more, else 'none'
// RESERVE adds 20% to the projected need. A window whose reset has passed gets no projection.
const WEEK_HOURS = 168
const MIN_ELAPSED_HOURS = 1
const RESERVE = 1.2
const SURPLUS_HIGH = 30
const SURPLUS_LOW = 15
type Projection = { burn_rate: number; projected_surplus: number; stage: 'high' | 'low' | 'none' }

const round = (v: number, digits: number) => Math.round(v * 10 ** digits) / 10 ** digits

const project = (w: Window): Projection | undefined => {
  const hoursLeft = (w.resets_at - w.seen_at) / 3600
  if (hoursLeft <= 0) return undefined
  const elapsed = WEEK_HOURS - hoursLeft
  const rate = elapsed >= MIN_ELAPSED_HOURS ? w.used_percentage / elapsed : 100 / WEEK_HOURS
  const surplus = 100 - w.used_percentage - hoursLeft * rate * RESERVE
  const stage = surplus >= SURPLUS_HIGH ? 'high' : surplus >= SURPLUS_LOW ? 'low' : 'none'
  return { burn_rate: round(rate, 3), projected_surplus: round(surplus, 1), stage }
}

// The stored window: the three measured fields, plus the projection for seven_day (recomputed on every write)
const stored = (k: Kind, w: Window) => {
  const base: Window = { used_percentage: w.used_percentage, resets_at: w.resets_at, seen_at: w.seen_at }
  return k === 'seven_day' ? { ...base, ...project(base) } : base
}

const toWindows = (limits: readonly SessionRateLimit[], seenAt: number): Snapshot => {
  const out: Snapshot = {}
  for (const l of limits) {
    if (!KINDS.includes(l.kind as Kind) || l.resetsAt === undefined) continue
    const resets = Date.parse(l.resetsAt)
    if (!Number.isFinite(resets) || !Number.isFinite(l.percentUsed)) continue
    out[l.kind as Kind] = {
      used_percentage: l.percentUsed,
      resets_at: Math.floor(resets / 1000),
      seen_at: seenAt,
    }
  }
  return out
}

// The output goes inside the user's private directory /tmp/claude-<uid>/ (uid is not in $.env, so run id -u).
// A predictable name directly under /tmp could make us write through a symlink another user planted first.
// The directory is used only if it is a real directory owned by the user with mode 700. $.fs.stat returns only the
// type and whether it is a link, not the owner and mode, so find (which does not follow a link at the starting
// point) checks "directory, owned by the user, 700" in one go.
async function filePath($: EngineInterface) {
  const idRun = await $.process.run(['id', '-u'])
  const uid = idRun.stdout.trim()
  if (idRun.exitCode !== 0 || !/^\d+$/.test(uid)) throw new Error('uid unavailable')
  const dir = `/tmp/claude-${uid}`
  // Create it with 700 if missing. If something already exists this just fails (no -p, so nothing is created through an existing link)
  await $.process.run(['mkdir', '-m', '700', dir]).catch(() => undefined)
  const found = await $.process.run(['find', dir, '-maxdepth', '0', '-type', 'd', '-user', uid, '-perm', '0700'])
  if (found.exitCode !== 0 || found.stdout.trim() !== dir) throw new Error('not a private directory')
  return `${dir}/rate-limits.json`
}

async function exportLimits($: EngineInterface, limits: readonly SessionRateLimit[]) {
  const seenAt = Math.floor((await $.clock.now()) / 1000)
  const incoming = toWindows(limits, seenAt)
  if (Object.keys(incoming).length === 0) return

  const file = await filePath($)
  let current: Snapshot = {}
  try {
    const parsed: unknown = JSON.parse(await $.fs.read(file))
    if (typeof parsed === 'object' && parsed !== null) {
      for (const k of KINDS) {
        const w = (parsed as Record<string, unknown>)[k]
        if (isWindow(w)) current[k] = w
      }
    }
  } catch {
    current = {} // missing or broken: rewrite with the new values
  }

  const merged: Snapshot = { ...current }
  let changed = false
  for (const k of KINDS) {
    const next = incoming[k]
    if (next !== undefined && isNewer(next, current[k])) {
      merged[k] = next
      changed = true
    }
  }
  if (!changed) return

  // Inside the private directory no other user can place anything. Write a temp file and mv -f it (rename is atomic).
  // On failure remove the tmp and do nothing (never fall back to writing directly; the next measure retries).
  const tmp = `${file}.${seenAt}.${Math.random().toString(36).slice(2, 8)}.tmp`
  const out: Record<string, unknown> = {}
  for (const k of KINDS) {
    const w = merged[k]
    if (w !== undefined) out[k] = stored(k, w)
  }
  try {
    await $.fs.write(tmp, JSON.stringify(out))
    const moved = await $.process.run(['mv', '-f', tmp, file])
    if (moved.exitCode === 0) return
  } catch {
    // the tmp is cleaned up below
  }
  await $.process.run(['rm', '-f', tmp]).catch(() => undefined)
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const started = await next(e)
    try {
      await exportLimits($, (await $.session.usage()).rateLimits)
    } catch {
      // a failed write must not stop the session
    }
    return started
  })

  on('session.measure', async ($, e, next) => {
    try {
      await exportLimits($, e.rateLimits)
    } catch {
      // same as above
    }
    return next(e)
  })
}
