# Changelog

Changes to the agent-bridge plugin. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions are the `version` in plugin.json.

## [0.1.0] - 2026-11-21

### Added
- First release: a message queue between Claude Code and other AI agents, hosted in the user's Supabase project (schema `agent_bridge` and Edge Function `agent-bridge`)
- One HTTP API for every agent with a per-agent token kept in Vault; agents are woken by webhook (the bridge POSTs through `pg_net`) or by polling an unauthenticated count-only status endpoint
- Rules in the schema: token to agent mapping, a per-thread message cap (`hop_limit`), claim-then-ack inbox, placeholder secrets that authenticate no one and webhooks that are not sent while placeholders
- `setup` skill (install, add a participant, check placeholders) and `talk` skill; MCP server with five tools; `wait_inbox.py` (`asyncRewake`) and `unread_notice.py` hooks
