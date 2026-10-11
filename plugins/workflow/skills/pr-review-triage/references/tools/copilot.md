# Copilot (id: `copilot`)

| Item | Details |
|---|---|
| Bot account name (full match on login) | `Copilot` / `copilot-pull-request-reviewer[bot]` |
| How it starts | Automatic depending on repo / organization settings. To request it ourselves, add it as a reviewer (the connector's `request_copilot_review`) |
| Done signal | A review (COMMENTED) |
| "No findings" signal | Not recorded |
| Rate-limit / quota signal (not reviewed) | Not recorded |
| Wait time | Not recorded |
| Heavy findings | Count the Critical/High equivalent (each tool labels severity differently) |
| How to request a re-review | `request_copilot_review` (not by comment) |
| Command to run locally | None |
