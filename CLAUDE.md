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
