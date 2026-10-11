import type { On, SessionRateLimit } from 'claude-code'
import { expect, mock, test } from 'claude-code/testing'

// Real examples in the shape seen on a real machine: 1791553800 = 2026-10-09T22:50:00+09:00, 1791615600 = 2026-10-10T16:00:00+09:00
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

// Replace the engine with an in-memory fs and id/mkdir/find/mv/rm. files holds the file contents.
// dir is the state of /tmp/claude-501: ok (owned by the user, 700) / missing / link / foreign (owned by someone else, or not 700).
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

test('measure writes five_hour and seven_day in the expected format', async ($, on) => {
  const s = world(on)
  await $.session.measure(measure([limit('five_hour', 17, FIVE), limit('seven_day', 75, SEVEN)]))
  expect(read(s)).toEqual({ five_hour: win(17, 1791553800), seven_day: win(75, 1791615600) })
  expect(Object.keys(s.files)).toEqual([FILE]) // no temp file is left behind
})

test('does not overwrite with an older value (smaller resets_at)', async ($, on) => {
  const old = { five_hour: win(30, 1791553800, NOW - 100), seven_day: win(75, 1791615600, NOW - 100) }
  const s = world(on, { [FILE]: JSON.stringify(old) })
  await $.session.measure(measure([limit('five_hour', 90, '2026-10-09T17:50:00+09:00'), limit('seven_day', 99, '2026-10-03T16:00:00+09:00')]))
  expect(read(s)).toEqual(old)
})

test('does not overwrite with lower usage for the same resets_at', async ($, on) => {
  const old = { five_hour: win(30, 1791553800, NOW - 100), seven_day: win(75, 1791615600, NOW - 100) }
  const s = world(on, { [FILE]: JSON.stringify(old) })
  await $.session.measure(measure([limit('five_hour', 29, FIVE), limit('seven_day', 75, SEVEN)]))
  expect(read(s)).toEqual(old)
})

test('a new week (larger resets_at) replaces even with lower usage', async ($, on) => {
  const old = { five_hour: win(30, 1791553800, NOW - 100), seven_day: win(75, 1791615600, NOW - 100) }
  const s = world(on, { [FILE]: JSON.stringify(old) })
  await $.session.measure(measure([limit('seven_day', 2, '2026-10-17T16:00:00+09:00')]))
  expect(read(s)).toEqual({ five_hour: old.five_hour, seven_day: win(2, 1792220400) })
})

test('ignores kinds other than five_hour / seven_day', async ($, on) => {
  const s = world(on)
  await $.session.measure(measure([limit('spend_limit', 120, SEVEN)]))
  expect(s.files[FILE]).toBeUndefined()
})

test('writes nothing when rateLimits is empty', async ($, on) => {
  const s = world(on)
  await $.session.measure(measure([]))
  expect(Object.keys(s.files)).toEqual([])
})

test('writes the new values even if the existing file is broken', async ($, on) => {
  const s = world(on, { [FILE]: '{"five_hour": {"used_perc' })
  await $.session.measure(measure([limit('five_hour', 17, FIVE)]))
  expect(read(s)).toEqual({ five_hour: win(17, 1791553800) })
})

test('creates the directory with 700 if missing, then writes', async ($, on) => {
  const s = world(on, {}, 'missing')
  await $.session.measure(measure([limit('five_hour', 17, FIVE)]))
  expect(s.ran).toContainEqual(['mkdir', '-m', '700', DIR])
  expect(read(s)).toEqual({ five_hour: win(17, 1791553800) })
})

test('writes nothing if the directory is a symlink', async ($, on) => {
  const s = world(on, {}, 'link')
  await $.session.measure(measure([limit('five_hour', 17, FIVE)]))
  expect(s.files).toEqual({})
  expect(s.ran.some(a => a[0] === 'mv')).toBe(false)
})

test('writes nothing if the directory is not owned by the user with 700', async ($, on) => {
  const s = world(on, {}, 'foreign')
  await $.session.measure(measure([limit('five_hour', 17, FIVE)]))
  expect(s.files).toEqual({})
})

test('stops writing once the directory later becomes owned by someone else', async ($, on) => {
  const s = world(on)
  await $.session.measure(measure([limit('five_hour', 17, FIVE)]))
  s.dir = 'foreign'
  await $.session.measure(measure([limit('five_hour', 50, FIVE)]))
  expect(read(s)).toEqual({ five_hour: win(17, 1791553800) })
})

test('if mv fails, does not write the real path and removes the temp file', async ($, on) => {
  const s = world(on)
  s.failMv = true
  await $.session.measure(measure([limit('five_hour', 17, FIVE)]))
  expect(s.files).toEqual({})
  expect(s.ran.some(a => a[0] === 'rm')).toBe(true)
})
