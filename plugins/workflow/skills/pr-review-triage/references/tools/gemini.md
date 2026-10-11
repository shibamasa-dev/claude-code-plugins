# Gemini Code Assist (id: `gemini`)

| Item | Details |
|---|---|
| Bot account name (full match on login) | `gemini-code-assist[bot]` |
| How it starts | Automatic on PR creation per the GitHub App settings. To request it ourselves, comment `/gemini review` |
| Done signal | A review (COMMENTED) |
| "No findings" signal | Not recorded |
| Rate-limit / quota signal (not reviewed) | Not recorded |
| Wait time | Not recorded |
| Heavy findings | Count the Critical/High equivalent (each tool labels severity differently) |
| How to request a re-review | Comment `/gemini review` (combined into one comment with requests to other tools) |
| Command to run locally | None |
