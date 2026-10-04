---
name: openapi-to-skills
description: >
  OpenAPI 3.0仕様をAIエージェント向けスキル形式（構造化Markdown）に変換する。
  Use when the user asks to "convert OpenAPI to skills", "OpenAPIをスキルに変換",
  "API specからスキルを生成", or wants to create agent skills from an API specification.
allowed-tools: [Bash]
last_reviewed: 2026-09-06
review_after: 2027-03-05
---

# OpenAPI to Skills Converter

OpenAPI 3.0仕様ファイル（YAML/JSON）をAIエージェント向けスキル形式に変換します。

## Prerequisites

- `uv` がインストールされていること
- 初回実行時に自動で依存ライブラリがインストールされます

## Usage

### 基本実行

```bash
uv run --project ${CLAUDE_PLUGIN_ROOT}/skills/openapi-to-skills ${CLAUDE_PLUGIN_ROOT}/skills/openapi-to-skills/scripts/convert.py <input> [options]
```

### Arguments

| Argument | Description |
|----------|-------------|
| `input` | OpenAPI specのファイルパス or URL |
| `-o, --output` | 出力ディレクトリ（デフォルト: `~/.claude/skills/`） |
| `-n, --name` | スキル名の上書き |
| `--include-tags` | 含めるタグ（カンマ区切り） |
| `--exclude-tags` | 除外するタグ（カンマ区切り） |
| `--exclude-paths` | 除外するパスプレフィックス（カンマ区切り） |
| `--exclude-deprecated` | 非推奨操作を除外 |
| `-g, --group-by` | グループ化戦略: `tags`, `path`, `auto`（デフォルト） |
| `-f, --force` | 既存出力を上書き |

### Examples

```bash
# ローカルファイルから変換
uv run --project ${CLAUDE_PLUGIN_ROOT}/skills/openapi-to-skills ${CLAUDE_PLUGIN_ROOT}/skills/openapi-to-skills/scripts/convert.py ./api-spec.yaml

# URLから変換
uv run --project ${CLAUDE_PLUGIN_ROOT}/skills/openapi-to-skills ${CLAUDE_PLUGIN_ROOT}/skills/openapi-to-skills/scripts/convert.py https://petstore3.swagger.io/api/v3/openapi.json

# 特定タグのみ変換
uv run --project ${CLAUDE_PLUGIN_ROOT}/skills/openapi-to-skills ${CLAUDE_PLUGIN_ROOT}/skills/openapi-to-skills/scripts/convert.py ./spec.yaml --include-tags users,products

# カスタム出力先
uv run --project ${CLAUDE_PLUGIN_ROOT}/skills/openapi-to-skills ${CLAUDE_PLUGIN_ROOT}/skills/openapi-to-skills/scripts/convert.py ./spec.yaml -o ./output
```

## Workflow

1. ユーザーからOpenAPI specのパスまたはURLを受け取る
2. 出力先を確認（デフォルト: `~/.claude/skills/`）
3. フィルタオプションがあれば適用
4. 上記コマンドを実行
