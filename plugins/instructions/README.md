# instructions

English | [日本語](README.ja.md)

A mod that loads instruction files bundled with the plugin the way Claude Code loads your own `~/.claude/CLAUDE.md`. Install it to get the same working rules on every machine without copying a CLAUDE.md around.

## Install

```text
/plugin marketplace add shibamasa-dev/claude-code-plugins
/plugin install instructions@shibamasa-plugins
```

## Instruction files

| File | What it says |
|---|---|
| `instructions/communication.md` | Reply in the user's language, concisely. Link files the user has to look at (PDFs, images, forms, drawings) as clickable relative paths, escape `(` `)` in file names, and send the file instead when the user reads from another device |

## Mods

| Mod | What it does |
|---|---|
| `register.ts` | On `prompt.context`, adds each file above to the instruction files as a `user` file, after your own `~/.claude/CLAUDE.md` and rules and before the project's `CLAUDE.md`. Claude Code then shows it in the same place and with the same framing as `~/.claude/CLAUDE.md`, and leaves it out where it leaves that file out (Explore, Plan and other subagents that omit CLAUDE.md) |

The context is built once per conversation and again after `/clear` or a compaction, so an edit to a file takes effect from the next of those. A file already among the instruction files (same path) isn't added twice. If another mod rewrote the CLAUDE.md text, the files behind it are unknown, and this mod adds nothing.

## Limitations

- **No effect where Claude Code's built-in guard runs.** On a machine with managed settings, or when you're signed in with a Team or Enterprise plan, Claude Code seats the built-in guard `sec-default@builtin`, which skips this mod's `prompt.context` hook for every plugin you install yourself. Nothing is shown in the conversation; the debug log has `prompt.context bypassed by cc-plugin-sec-default (tier user)`. Only managed settings can change that: a managed `prependPlugins` list that leaves out `sec-default@builtin` keeps the guard from loading, which also drops its other protections against plugins you install (see [Manage mods for your organization](https://code.claude.com/docs/en/plugins/mods/admin)).
- The files are English. Claude still replies in your language.

## Requirements

Claude Code v2.1.287 or later in the terminal, or v2.1.286 or later in the Desktop app's Code tab (mods are on by default from those versions)

## Tests

```bash
claude plugin test plugins/instructions
```
