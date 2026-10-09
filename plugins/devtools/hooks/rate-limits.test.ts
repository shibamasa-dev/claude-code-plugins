import type { On, SessionRateLimit } from 'claude-code'
import { expect, mock, test } from 'claude-code/testing'

// 値は実機で見た形に合わせた実例: 1791553800 = 2026-10-09T22:50:00+09:00, 1791615600 = 2026-10-10T16:00:00+09:00
const FILE = '/tmp/claude-rate-limits-501.json'
const TMP = '/tmp/claude-rate-limits.AbC123'
const NOW = 1791552278
const FIVE = '2026-10-09T22:50:00+09:00'
const SEVEN = '2026-10-10T16:00:00+09:00'

const limit = (kind: string, percentUsed: number, resetsAt?: string): SessionRateLimit => ({ kind, percentUsed, resetsAt })
const measure = (rateLimits: SessionRateLimit[]) => ({
  context: { window: 200000 },
  rateLimits,
  changed: ['rateLimits' as const],
})

// エンジンの代わりにメモリ上の fs と id/mktemp/mv/rm を置く。files がファイルの中身、links がシンボリックリンクのパス。
const world = (on: On, files: Record<string, string> = {}) => {
  const state = { files, links: new Set<string>(), failMktemp: false, failMv: false, ran: [] as string[] }
  mock.clock(on, { now: NOW * 1000 })
  on('fs.read', (_$, e) => {
    const text = state.files[e.path]
    if (text === undefined) return { deny: 'ENOENT' }
    return { value: text }
  })
  on('fs.write', (_$, e) => {
    // 書き込みはリンクを辿る: リンクならリンク先ではなく /victim に落ちる
    state.files[state.links.has(e.path) ? '/victim' : e.path] = e.text
    return { value: undefined }
  })
  on('process.run', (_$, e) => {
    const [cmd, a, b, c] = e.argv
    state.ran.push(cmd ?? '')
    const ok = { exitCode: 0, stdout: '', stderr: '' }
    const fail = { exitCode: 1, stdout: '', stderr: 'failed' }
    if (cmd === 'id') return { value: { ...ok, stdout: '501\n' } }
    if (cmd === 'mktemp') return { value: state.failMktemp ? fail : { ...ok, stdout: `${TMP}\n` } }
    if (cmd === 'mv' && a === '-f' && b !== undefined && c !== undefined) {
      if (state.failMv) return { value: fail }
      state.files[c] = state.files[b] ?? '' // rename は宛先のリンクを辿らず置き換える
      state.links.delete(c)
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

test('書き込み先がシンボリックリンクでもリンク先は書き換えず、リンク自体を置き換える', async ($, on) => {
  const s = world(on, { '/victim': 'secret' })
  s.links.add(FILE)
  await $.session.measure(measure([limit('five_hour', 17, FIVE)]))
  expect(s.files['/victim']).toBe('secret')
  expect(s.links.has(FILE)).toBe(false)
  expect(read(s)).toEqual({ five_hour: win(17, 1791553800) })
})

test('mv が失敗したら本番パスへ書かずに一時ファイルを消す', async ($, on) => {
  const s = world(on)
  s.failMv = true
  await $.session.measure(measure([limit('five_hour', 17, FIVE)]))
  expect(s.files).toEqual({})
  expect(s.ran).toContain('rm')
})

test('mktemp が失敗したら何もしない', async ($, on) => {
  const s = world(on)
  s.failMktemp = true
  await $.session.measure(measure([limit('five_hour', 17, FIVE)]))
  expect(s.files).toEqual({})
  expect(s.ran).not.toContain('mv')
})
