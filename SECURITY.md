# Security

If you find a way around the guards hooks, or a vulnerability in a hook or script, don't open a public issue. Report it privately through GitHub's [Report a vulnerability](https://github.com/shibamasa-dev/claude-code-plugins/security/advisories/new).

## Scope

- The latest `main`
- Code in `plugins/*/hooks/`, `plugins/*/bin/` and `plugins/*/skills/*/scripts/`
- `.github/workflows/` and `.githooks/`

guards is a safety net against Claude's mistakes, not a sandbox against malicious commands. The fact that it can't be used as a sandbox isn't treated as a vulnerability.
