import type { InstructionFile, Register } from 'claude-code'

// Loads the files under instructions/ as the person's own instruction files (kind "user"),
// so the engine renders them inside the claudeMd block next to ~/.claude/CLAUDE.md, with the same framing
// and the same rules for subagents. Listed by name so the order is fixed.
const FILES = ['communication.md']

// Instruction files come in load order: managed, user, project, local, memory.
// Ours go after the last managed or user file, before the project's.
const insertAt = (files: readonly InstructionFile[]): number => {
  let at = 0
  files.forEach((f, i) => {
    if (f.kind === 'managed' || f.kind === 'user') at = i + 1
  })
  return at
}

export const register: Register = on => {
  on('prompt.context', async ($, e, next) => {
    const r = await next(e)
    const files = r.instructionFiles
    // undefined: a hook rewrote the claudeMd text, so the files behind it are unknown; add nothing
    if (files === undefined) return r
    const ours: InstructionFile[] = []
    for (const name of FILES) {
      const path = `${$.plugin.root}/instructions/${name}`
      if (files.some(f => f.path === path)) continue
      ours.push({ path, kind: 'user', content: await $.fs.read(path) })
    }
    if (ours.length === 0) return r
    const at = insertAt(files)
    return { ...r, instructionFiles: [...files.slice(0, at), ...ours, ...files.slice(at)] }
  })
}
