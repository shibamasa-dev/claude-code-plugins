# Changelog

Changes to the agent-bridge plugin. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions are the `version` in plugin.json.

## [0.2.2] - 2026-11-22

### Changed
- `setup` skill: asks "Should this Claude Code session wake up when a message arrives?" and sets `listen` (and `poll_seconds`) from the answer, with the trade-off (outside messages start turns, cost per poll, scope of the install). `listen` still defaults to `false`
- `setup` and `add` skills: ask which external services the agent is connected to and what it can do there, and put the answer in `capabilities`. `add` documents that running `register_participant` again overwrites `wake`, `display_name`, `role` and `capabilities`, and gives the `UPDATE` that changes `capabilities` alone
- `setup` skill: the settings step spells out `claude plugin configure --values-stdin` (string values only, a JSON boolean is rejected; a local or project install is configured from that project's folder), with an example
- `setup` and `add` skills finish by telling the user to run `/reload-plugins` in every running session after options change (a running session keeps old option values and the plugin version it loaded), where the tables are (schema `agent_bridge`, with the dashboard link) and how to work out the polling cost
- README (both languages): the same notes under Configuration, a Capabilities entry under How it works, and a fuller `listen` description

## [0.2.1] - 2026-11-22

### Changed
- `add` skill: asks whether the agent should answer (a receive-only webhook agent needs no bridge token), who checks a webhook's bearer key, and whether an earlier proof-of-concept route should be retired
- `add` skill: webhook URL and key come from the agent's platform; a table says where to copy each value from and where to paste it. Gives the Vault dashboard path for editing secrets
- `add` skill: the token is handed over through the agent's own secret-input card, with the request format in the same message, so Claude never types it. Notes the per-host permission prompt (a poll agent needs "always"). Instruction text must hold no angle-bracket placeholders and every URL in full
- `add` skill verify step: the agent itself confirms `me`; Claude sends a test message through the connector without exposing a token and reads the outcome, including a webhook's HTTP status from `net._http_response`; a receive-only webhook agent's unused token is expected to stay a placeholder and its token check is skipped
- `instructions-poll.md`, `instructions-webhook.md`: token may be an environment variable or a stored credential, stated to be a per-agent bridge token and not a Supabase API key; a request-format section and the proof that a token works (`me`; an HTTP 400 proves nothing; the first call can take about 30 seconds); no angle-bracket placeholders. The webhook template offers answering or receive-only and a self-check or platform-verified key
- `token-route.md`: the Vault write prints `"updated": 1` on success (it printed `false` before), `0` for an unknown secret name; `tok` is kept until the agent itself has confirmed `me`; one agent at a time; the dashboard path for Vault

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
