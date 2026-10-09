import type { On, SessionRateLimit } from 'claude-code'
import { expect, mock, test } from 'claude-code/testing'

// 値は実機で見た形に合わせた実例: 1791553800 = 2026-10-09T22:50:00+09:00, 1791615600 = 2026-10-10T16:00:00+09:00
const DIR = '/tmp/claude-501'
const FILE = `${DIR}/rate-limits.json`
const NOW = 1791552278
const FIVE = '2026-10-09T22:50:00+09:00'
const SEVEN = '2026-10-10T16:00:00+09:00'

const limit = (kind: string, percentUsed: number, resetsAt?: string): SessionRateLimit => ({ kind, percentUsed, resetsAt })
const measure = (rateLimits: SessionRateLimit[]) => ({
  context: { window: 200000 },
  rateLimits,
  changed: ['rateLimits' as const],
})

// エンジンの代わりにメモリ上の fs と id/mkdir/find/mv/rm を置く。files がファイルの中身。
// dir は /tmp/claude-501 の状態: ok（本人所有 700）/ missing / link / foreign（他人所有か 700 でない）。
const world = (on: On, files: Record<string, string> = {}, dir: 'ok' | 'missing' | 'link' | 'foreign' = 'ok') => {
  const state = { files, dir, failMv: false, ran: [] as string[][] }
  mock.clock(on, { now: NOW * 1000 })
  on('fs.read', (_$, e) => {
    const text = state.files[e.path]
    if (text === undefined) return { deny: 'ENOENT' }
    return { value: text }
  })
  on('fs.write', (_$, e) => {
    state.files[e.path] = e.text
    return { value: undefined }
  })
  on('process.run', (_$, e) => {
    const [cmd, a, b, c] = e.argv
    state.ran.push([...e.argv])
    const ok = { exitCode: 0, stdout: '', stderr: '' }
    const fail = { exitCode: 1, stdout: '', stderr: 'failed' }
    if (cmd === 'id') return { value: { ...ok, stdout: '501\n' } }
    if (cmd === 'mkdir') {
      if (state.dir !== 'missing') return { value: fail }
      state.dir = 'ok'
      return { value: ok }
    }
    if (cmd === 'find') return { value: state.dir === 'ok' ? { ...ok, stdout: `${a}\n` } : fail }
    if (cmd === 'mv' && a === '-f' && b !== undefined && c !== undefined) {
      if (state.failMv) return { value: fail }
      state.files[c] = state.files[b] ?? ''
      delete state.files[b]
    }
    if (cmd === 'rm') delete state.files[b === '-f' ? (c ?? '') : (b ?? '')]
    return { value: ok }
  })
  on('session.measure', (_$, e) => ({ changed: e.changed }))
  return state
}
const read = (s: { files: Record<string, string> }) => JSON.parse(s.files[FILE] ?? 'null')
const win = (used_percentage: number, resets_at: number, seen_at = NOW) => ({ used_percentage, resets_at, seen_at })

test('measure で five_hour と seven_day を所定の形式で書く', async ($, on) => {
  const s = world(on)
  await $.session.measure(measure([limit('five_hour', 17, FIVE), limit('seven_day', 75, SEVEN)]))
  expect(read(s)).toEqual({ five_hour: win(17, 1791553800), seven_day: win(75, 1791615600) })
  expect(Object.keys(s.files)).toEqual([FILE]) // 一時ファイルは残らない
})

test('resets_at が小さい古い値では上書きしない', async ($, on) => {
  const old = { five_hour: win(30, 1791553800, NOW - 100), seven_day: win(75, 1791615600, NOW - 100) }
  const s = world(on, { [FILE]: JSON.stringify(old) })
  await $.session.measure(measure([limit('five_hour', 90, '2026-10-09T17:50:00+09:00'), limit('seven_day', 99, '2026-10-03T16:00:00+09:00')]))
  expect(read(s)).toEqual(old)
})

test('resets_at が同じで使用率が小さい値では上書きしない', async ($, on) => {
  const old = { five_hour: win(30, 1791553800, NOW - 100), seven_day: win(75, 1791615600, NOW - 100) }
  const s = world(on, { [FILE]: JSON.stringify(old) })
  await $.session.measure(measure([limit('five_hour', 29, FIVE), limit('seven_day', 75, SEVEN)]))
  expect(read(s)).toEqual(old)
})

test('新しい週（resets_at が大きい）は使用率が小さくても置き換える', async ($, on) => {
  const old = { five_hour: win(30, 1791553800, NOW - 100), seven_day: win(75, 1791615600, NOW - 100) }
  const s = world(on, { [FILE]: JSON.stringify(old) })
  await $.session.measure(measure([limit('seven_day', 2, '2026-10-17T16:00:00+09:00')]))
  expect(read(s)).toEqual({ five_hour: old.five_hour, seven_day: win(2, 1792220400) })
})

test('five_hour / seven_day 以外の kind は無視する', async ($, on) => {
  const s = world(on)
  await $.session.measure(measure([limit('spend_limit', 120, SEVEN)]))
  expect(s.files[FILE]).toBeUndefined()
})

test('rateLimits が空なら書かない', async ($, on) => {
  const s = world(on)
  await $.session.measure(measure([]))
  expect(Object.keys(s.files)).toEqual([])
})

test('既存ファイルが壊れていても新しい値で書ける', async ($, on) => {
  const s = world(on, { [FILE]: '{"five_hour": {"used_perc' })
  await $.session.measure(measure([limit('five_hour', 17, FIVE)]))
  expect(read(s)).toEqual({ five_hour: win(17, 1791553800) })
})

test('ディレクトリが無ければ 700 で作って書く', async ($, on) => {
  const s = world(on, {}, 'missing')
  await $.session.measure(measure([limit('five_hour', 17, FIVE)]))
  expect(s.ran).toContainEqual(['mkdir', '-m', '700', DIR])
  expect(read(s)).toEqual({ five_hour: win(17, 1791553800) })
})

test('ディレクトリがシンボリックリンクなら何も書かない', async ($, on) => {
  const s = world(on, {}, 'link')
  await $.session.measure(measure([limit('five_hour', 17, FIVE)]))
  expect(s.files).toEqual({})
  expect(s.ran.some(a => a[0] === 'mv')).toBe(false)
})

test('ディレクトリが本人所有の 700 でなければ何も書かない', async ($, on) => {
  const s = world(on, {}, 'foreign')
  await $.session.measure(measure([limit('five_hour', 17, FIVE)]))
  expect(s.files).toEqual({})
})

test('mv が失敗したら本番パスへ書かずに一時ファイルを消す', async ($, on) => {
  const s = world(on)
  s.failMv = true
  await $.session.measure(measure([limit('five_hour', 17, FIVE)]))
  expect(s.files).toEqual({})
  expect(s.ran.some(a => a[0] === 'rm')).toBe(true)
})
