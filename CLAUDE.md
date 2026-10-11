# claude-code-plugins-public

## プラグイン・MCPサーバーを作るときの参照先

仕様の判断は公式ドキュメントで裏を取る。公式の plugin-dev スキル（v0.1.0）は古く、`userConfig`、`mcp_tool` フック、`${CLAUDE_PLUGIN_DATA}`、`.mcpb` が載っていない。設定値は `.claude/<plugin>.local.md` に書く旧方式で案内してくるので、骨組みの参考までにする。mcp-builder スキルは MCP 仕様を読みに行くが、Claude 側の機能（MCP Apps など）は見ない。

1. プラグイン：https://code.claude.com/docs/en/plugins-reference （plugin.json、`userConfig`、環境変数）
2. フック：https://code.claude.com/docs/en/hooks （`mcp_tool` フックなど）
3. 設定：https://code.claude.com/docs/en/settings-reference （`pluginConfigs` など）
4. Claude Code の最新の変更：https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md
5. MCP 仕様：https://modelcontextprotocol.io/specification/latest と https://blog.modelcontextprotocol.io
6. API の MCP connector：https://platform.claude.com/docs/en/agents-and-tools/mcp-connector

社内の値はこのリポジトリに書かない（組織で固定の値は組織側のプラグインが注入する）。人ごとの値は `userConfig` で受けて `${user_config.KEY}` で参照する。

## PR レビュー

review-heavy: coderabbit, codex

## Plugins that persist state

Who installs a plugin decides where its data lives (SQLite, Postgres, Supabase) and how it is reached (a direct connection or a claude.ai connector). Build for that instead of hard-coding one store.

1. Store: SQLite under `${CLAUDE_PLUGIN_DATA}` by default, so the plugin works with no setup. `sqlite_path` moves it; `database_url` (a `sensitive` `userConfig` option) connects to Postgres or Supabase directly. Say in the README that uninstalling deletes `${CLAUDE_PLUGIN_DATA}`, and the database with it, unless `--keep-data` is passed.
2. Route: a direct connection or a connector. Decide once, on first use, and have Claude save the result in `userConfig`. When the saved route is unavailable, stop and tell the user; never fall back to another store, or the data splits across two places. Find a connector by what it can do (runs SQL), not by tool name, because the server part of the name differs per user, and save its ID and any `project_id` it needs. Supabase's `execute_sql` takes only a query string, with no separate parameters.
3. Runner for a direct connection: an MCP server bundled with the plugin, limited to running SQL, applying migrations and the normalization functions. A `sensitive` value reaches only an MCP server's `env` and hooks; skill content gets a placeholder and Bash commands get nothing.
4. SQL: Claude writes it. The plugin ships the schema and registration examples. Stick to SQL that runs on both SQLite and Postgres (`INSERT ... ON CONFLICT DO UPDATE`, `TEXT` / `INTEGER`, JSON and timestamps stored as text).
5. Rules that must hold on every write live in the schema (constraints, generated columns, triggers), so they hold whoever writes the SQL. Only a rule the schema can't express on both databases becomes a small function, such as NFKC normalization (SQLite has no `normalize()`).
6. Schema changes apply automatically and idempotently. Never ask the user to run an `ALTER` by hand. Over a connector, send DDL through the connector's migration tool (Supabase: `apply_migration`).
7. Extension points: every table has a stable primary key and `updated_at`. Optional features such as vector search add no columns to the plugin's schema; whoever wants one adds their own column or table and a hook (for example `PostToolUse` matched to the tools that touch the database) and uses `updated_at` to find rows to refresh.
