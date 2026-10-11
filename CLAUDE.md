# claude-code-plugins-public

## References for building plugins and MCP servers

Verify spec questions against the official docs. The official plugin-dev skill (v0.1.0) is outdated: it doesn't cover `userConfig`, `mcp_tool` hooks, `${CLAUDE_PLUGIN_DATA}` or `.mcpb`, and it still suggests the old `.claude/<plugin>.local.md` settings files, so use it only as a skeleton. The mcp-builder skill reads the MCP spec but not Claude-side features such as MCP Apps.

1. Plugins: https://code.claude.com/docs/en/plugins-reference (plugin.json, `userConfig`, environment variables)
2. Hooks: https://code.claude.com/docs/en/hooks (`mcp_tool` hooks and more)
3. Settings: https://code.claude.com/docs/en/settings-reference (`pluginConfigs` and more)
4. Latest Claude Code changes: https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md
5. MCP spec: https://modelcontextprotocol.io/specification/latest and https://blog.modelcontextprotocol.io
6. MCP connector in the API: https://platform.claude.com/docs/en/agents-and-tools/mcp-connector

Never write internal company values in this repo (organization-wide values are injected by the organization's own plugin). Take per-user values through `userConfig` and reference them as `${user_config.KEY}`.

## Language

This is a public repo for users worldwide, so English is the base language.

- Write in English: skill bodies and `references/`, hook and script messages, comments, tests, commands, `plugin.json` / `marketplace.json` descriptions and `userConfig` titles, new CHANGELOG entries, issue and PR templates, commit messages and PR titles
- Japanese goes only in `README.ja.md`. Nothing else gets a translation; Claude replies in the user's language anyway
- Exceptions where Japanese stays:
  - Skill `description` frontmatter: English first, then the Japanese trigger phrases (for example 「閉じたい」「残件確認して」). Triggering matches the language of the user's prompt, so dropping them breaks Japanese prompts
  - Data the feature needs: regexes or keywords that match Japanese text, fixtures and eval prompts that represent Japanese input, detectors that still accept an older Japanese marker
  - CHANGELOG entries written before the switch to English (don't rewrite history)
- Where a skill says which language to answer in, say "the user's language", not a fixed language

## READMEs

The layout follows Anthropic's plugin repos (anthropics/claude-plugins-official, anthropics/claude-code `plugins/`, anthropics/knowledge-work-plugins): one README at the root and one per plugin, no separate docs tree.

- Place: `README.md` at the root and in every `plugins/<name>/`, each with a `README.ja.md` next to it
- Line 3 of both files is the language switcher: `English | [日本語](README.ja.md)` in README.md, `[English](README.md) | 日本語` in README.ja.md. Links inside README.ja.md point to other `README.ja.md` files
- Change both files in the same PR, with the same sections in the same order
- Root README sections: title, switcher, badges, one-line purpose, a trust note (plugins run code on your machine), Install (`/plugin marketplace add` → `/plugin install`), Plugins table (name → what it does, linked to the plugin README), Language, Requirements, Contributing, License. Keep a migration section only while a rename is recent
- Plugin README sections, roughly in this order, omitting ones that don't apply: title, switcher, one-line summary, Install, Skills (skill / use it for), Hooks (hook / when / what it does), Mods, Commands, Configuration (`userConfig` keys: key / default / meaning, plus per-repo overrides), Limitations, Requirements, Tests
- Describe the current behavior only. Version history and reasons for past changes go in CHANGELOG.md
- `.github/scripts/check-repo.py` enforces the pair, the switcher links and the absence of kana in `README.md`

## PR reviews

review-heavy: coderabbit, codex
