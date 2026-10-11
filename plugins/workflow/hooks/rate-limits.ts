import type { Engine, Register, SessionRateLimit } from 'claude-code'

// Write the usage limits (rate limits) to /tmp/claude-<uid>/rate-limits.json.
// An external script that watches the remaining weekly quota reads it. Format:
// {"five_hour": {"used_percentage": 17, "resets_at": 1791553800, "seen_at": 1791552278}, "seven_day": {...}}

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
async function filePath($: Engine) {
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

async function exportLimits($: Engine, limits: readonly SessionRateLimit[]) {
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
  try {
    await $.fs.write(tmp, JSON.stringify(merged))
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
