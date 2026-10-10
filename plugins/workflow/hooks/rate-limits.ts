import type { Engine, Register, SessionRateLimit } from 'claude-code'

// 使用枠（rate limits）を /tmp/claude-<uid>/rate-limits.json に書き出す。
// 週の残り枠を見張る外部スクリプトが読む。形式:
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

// 新しい窓（resets_at が大きい）が勝ち、同じ窓なら使用率が大きい方が勝つ。使用率はリセットまで減らない。
// 並列セッションの古い値で上書きしないための規則。
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

// 出力は本人専用ディレクトリ /tmp/claude-<uid>/ の中に置く（uid は $.env に無いので id -u を叩く）。
// /tmp 直下の予測できる名前だと、他ユーザーが先に置いたシンボリックリンクの先を書かされる。
// ディレクトリは本人所有・700 の実体でなければ使わない。$.fs.stat は種別とリンクしか返さず所有者と権限が
// 取れないので、find（開始点のリンクを辿らない）で「ディレクトリ・本人所有・700」を一度に確かめる。
async function filePath($: Engine) {
  const idRun = await $.process.run(['id', '-u'])
  const uid = idRun.stdout.trim()
  if (idRun.exitCode !== 0 || !/^\d+$/.test(uid)) throw new Error('uid unavailable')
  const dir = `/tmp/claude-${uid}`
  // 無ければ 700 で作る。何かが既にあれば失敗するだけ（-p を付けないので既存のリンクの先には作らない）
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
    current = {} // 無い・壊れている: 新しい値で書き直す
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

  // 本人専用ディレクトリの中なので他ユーザーは何も置けない。一時ファイルに書いて mv -f（rename は原子的）。
  // 失敗したら tmp を消して何もしない（直書きには落とさない。次の measure で再試行される）。
  const tmp = `${file}.${seenAt}.${Math.random().toString(36).slice(2, 8)}.tmp`
  try {
    await $.fs.write(tmp, JSON.stringify(merged))
    const moved = await $.process.run(['mv', '-f', tmp, file])
    if (moved.exitCode === 0) return
  } catch {
    // 下で tmp を片付ける
  }
  await $.process.run(['rm', '-f', tmp]).catch(() => undefined)
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const started = await next(e)
    try {
      await exportLimits($, (await $.session.usage()).rateLimits)
    } catch {
      // 書き出しの失敗でセッションを止めない
    }
    return started
  })

  on('session.measure', async ($, e, next) => {
    try {
      await exportLimits($, e.rateLimits)
    } catch {
      // 同上
    }
    return next(e)
  })
}
