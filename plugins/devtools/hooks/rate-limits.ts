import type { Engine, Register, SessionRateLimit } from 'claude-code'

// 使用枠（rate limits）を /tmp/claude-rate-limits-<uid>.json に書き出す。
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

let path: string | undefined

// ファイル名は実行ユーザーの uid で決める（$.env に UID は無いので id -u を一度だけ叩く）
async function filePath($: Engine) {
  if (path !== undefined) return path
  const { exitCode, stdout } = await $.process.run(['id', '-u'])
  const uid = stdout.trim()
  if (exitCode !== 0 || !/^\d+$/.test(uid)) throw new Error('uid unavailable')
  path = `/tmp/claude-rate-limits-${uid}.json`
  return path
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

  // /tmp の予測できる名前に別ユーザーが置いたシンボリックリンクを辿って書かない。
  // $.fs.stat は path 自身の isLink を返す（lstat 相当）。対象が既にリンクなら書かない。
  const target = await $.fs.stat(file).catch(() => undefined)
  if (target?.isLink === true) return

  // 一時ファイルに書いて mv（同じディレクトリ内の rename は原子的）。読む側が書きかけを見ない。
  const tmp = `${file}.${seenAt}.${Math.random().toString(36).slice(2, 8)}.tmp`
  const text = JSON.stringify(merged)
  // 一時ファイルも、既にあれば（リンクでも通常ファイルでも）使わない。名前は乱数で予測しにくい
  if (await $.fs.stat(tmp).then(() => true, () => false)) return
  await $.fs.write(tmp, text)
  const moved = await $.process.run(['mv', '-f', tmp, file]).catch(() => undefined)
  if (moved?.exitCode !== 0) {
    await $.process.run(['rm', '-f', tmp]).catch(() => undefined)
    // 直書きに落とす前にもう一度リンクを確かめる
    const again = await $.fs.stat(file).catch(() => undefined)
    if (again?.isLink === true) return
    await $.fs.write(file, text) // rename できない環境では非原子的な直書きに落とす
  }
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
