# Cursor Bugbot (id: `cursor-bugbot`)

| Item | Details |
|---|---|
| Bot account name (full match on login) | `cursor[bot]` |
| How it starts | Automatic on PR creation per the GitHub App settings (watch out for usage-based billing). To request it ourselves, comment `bugbot run` |
| Done signal | A review (with findings) |
| "No findings" signal | A review (no findings) |
| Rate-limit / quota signal (not reviewed) | A limit-reached comment |
| Wait time | Not recorded. A limit gets no response to our requests, so ask the user to lift it |
| Heavy findings | Count the Critical/High equivalent (each tool labels severity differently) |
| How to request a re-review | Comment `bugbot run` (combined into one comment with requests to other tools) |
| Command to run locally | None |
