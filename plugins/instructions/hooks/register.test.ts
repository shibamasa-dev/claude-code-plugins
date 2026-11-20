import type { InstructionFile, On } from 'claude-code'
import { expect, test } from 'claude-code/testing'

// The instruction files a real session handed to prompt.context (Claude Code 2.1.296, macOS),
// in the same order and kinds. The home directory and project paths are replaced; contents are cut short.
const HOME = '/tmp/home'
const REAL: InstructionFile[] = [
  { path: `${HOME}/.claude/CLAUDE.md`, kind: 'user', content: '# Global rules' },
  { path: `${HOME}/.claude/rules/local-env.md`, kind: 'user', content: '# Local environment' },
  { path: `${HOME}/.claude/rules/asset-generation.md`, kind: 'user', content: '# Asset generation' },
  { path: `${HOME}/dev/app/CLAUDE.md`, kind: 'project', content: '# app' },
  { path: `${HOME}/.claude/projects/-tmp-home-dev-app/memory/MEMORY.md`, kind: 'memory', content: '- [note](note.md)' },
]
const BLOCKS = [
  { name: 'claudeMd', text: '...' },
  { name: 'currentDate', text: "Today's date is 2026-10-12." },
]
const TEXT = '# Communication\n'

// The engine beneath: answers the files as handed, and serves the bundled file from fs.read.
// The test's $ has no plugin root, so the path the mod reads is recorded and compared instead.
const SUFFIX = '/instructions/communication.md'
const world = (on: On) => {
  const read: string[] = []
  on('fs.read', (_$, e) => {
    if (!e.path.endsWith(SUFFIX)) return { deny: 'ENOENT' }
    read.push(e.path)
    return { value: TEXT }
  })
  on('prompt.context', (_$, e) => ({ blocks: e.blocks, instructionFiles: e.instructionFiles }))
  return read
}
const ours = (path: string): InstructionFile => ({ path, kind: 'user', content: TEXT })

test('adds the bundled file as a user file after the last user file', async ($, on) => {
  const read = world(on)
  const r = await $.prompt.context({ blocks: BLOCKS, instructionFiles: REAL })
  expect(read).toHaveLength(1)
  expect(read[0]?.startsWith('/')).toBe(true)
  expect(r.instructionFiles).toEqual([...REAL.slice(0, 3), ours(read[0] ?? ''), ...REAL.slice(3)])
  // the engine renders the claudeMd block again from the files, framing ours as it frames ~/.claude/CLAUDE.md
  expect(r.blocks.find(b => b.name === 'claudeMd')?.text).toContain(
    `Contents of ${read[0]} (user's private global instructions for all projects):\n\n${TEXT}`,
  )
})

test('goes first when there is no managed or user file', async ($, on) => {
  const read = world(on)
  const r = await $.prompt.context({ blocks: BLOCKS, instructionFiles: REAL.slice(3) })
  expect(r.instructionFiles).toEqual([ours(read[0] ?? ''), ...REAL.slice(3)])
})

test('adds nothing when a hook rewrote the claudeMd text', async ($, on) => {
  world(on)
  const r = await $.prompt.context({ blocks: BLOCKS })
  expect(r.instructionFiles).toBeUndefined()
  expect(r.blocks).toEqual(BLOCKS)
})

test('does not add the file twice', async ($, on) => {
  // a first run learns the path the mod uses, a second run hands that file back already loaded
  const read = world(on)
  await $.prompt.context({ blocks: BLOCKS, instructionFiles: REAL })
  const loaded = [...REAL, ours(read[0] ?? '')]
  const r = await $.prompt.context({ blocks: BLOCKS, instructionFiles: loaded })
  expect(r.instructionFiles).toEqual(loaded)
})
