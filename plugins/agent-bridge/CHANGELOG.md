# Changelog

Changes to the agent-bridge plugin. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions are the `version` in plugin.json.

## [0.2.0] - 2026-11-22

### Changed
- `setup` no longer has an add mode: adding an agent moved to the `add` skill, and its description lost the add triggers
- `setup` skill asks for the install scope (which repo's sessions use the bridge) and this environment's `agent_id` before installing, instead of registering `claude` silently
- `setup` skill: the approval message says when the target project is production; ends by saying settings take effect only in a new session
- `setup` check mode makes an authenticated call (`me` in the answer) to prove that the plugin's `token` equals the Vault secret, which `doctor()` and the unauthenticated status endpoint cannot show

### Added
- `add` skill: connecting another agent as its own skill (ask for id, name, role and capabilities and how it is woken; register it; hand over its token; write the instructions to give the agent, from a poll or a webhook template; verify with `doctor()` and an authenticated call). `setup` keeps install and check, and registers Claude Code through the `add` skill's registration step
- Shared references: `references/connector.md` (connector and project discovery) and `references/token-route.md` (the shell route for the token and the authenticated call), used by both skills
- `setup` skill: optional route where Claude sets the token without seeing it (generated in the shell, saved with `claude plugin configure`, written to Vault with the user's Supabase CLI after the user's explicit OK), with the clipboard and the manual steps as fallbacks
- README: install scope note (options are saved per user whatever the scope)

## [0.1.0] - 2026-11-21

### Added
- First release: a message queue between Claude Code and other AI agents, hosted in the user's Supabase project (schema `agent_bridge` and Edge Function `agent-bridge`)
- One HTTP API for every agent with a per-agent token kept in Vault; agents are woken by webhook (the bridge POSTs through `pg_net`) or by polling an unauthenticated count-only status endpoint
- Rules in the schema: token to agent mapping, a per-thread message cap (`hop_limit`), claim-then-ack inbox, only thread members write to a thread, invalid input rejected as `bad_request`, placeholder secrets that authenticate no one and webhooks that are not sent while placeholders
- `setup` skill (install, add a participant, check placeholders) and `talk` skill; MCP server with five tools; `wait_inbox.py` (`asyncRewake`, only in sessions that used a bridge tool, marked by `arm_session.py`) and `unread_notice.py` hooks
