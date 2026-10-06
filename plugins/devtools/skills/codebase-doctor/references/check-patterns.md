# Check Patterns by Language

Per-language Grep/Glob patterns for each check. All regex patterns use **rg syntax** (`|` for alternation, no escaping needed for `|`).

If the detected language is not listed below, infer patterns from its ecosystem. Mark results with `[inferred]`.

## AI Agent Guidelines (language-agnostic, run first)

| Check | Glob | What to verify |
|-------|------|---------------|
| File exists | `AGENTS.md` `CLAUDE.md` `.cursorrules` `COPILOT.md` `CONVENTIONS.md` | At least one present |
| Tech stack defined | (Read file) | Language, framework, major dependencies mentioned |
| Commands defined | (Read file) | Build, test, lint, run commands documented |
| Conventions defined | (Read file) | Logging, error handling, naming, or other coding rules |

If found, extract project-specific rules and use them to calibrate subsequent checks.

## Test-design knowledge layer (Check 6b, language-agnostic)

Presence only — never judge the contents. Paths are **not** defined here; read
`references/perspectives-common.md` of the `testcase-generator` skill (testing plugin;
section "プロジェクト固有の観点") and use what it says. A second copy of the layout
in this file would drift from the first one. Without the testing plugin, report the check as not run.

| Applies | When |
|---|---|
| perspectives file | always |
| UI-terms file | only when the detected stack renders something a person operates (frontend framework, server-side templates, static assets served to a client). Backend-only API / batch / ETL / CLI / library → does not apply |
| playbook file | tests exist, or the phase is `test` |

## Project Configuration (language-agnostic)

Agent working environment. All checks are diff-based — read the current state, compare against what the phase needs, propose only the gap.

| Check | Where to look | What to verify |
|-------|---------------|----------------|
| Agent Permissions | `.claude/settings.json` `.claude/settings.local.json` | `permissions.allow` covers the build/test/lint commands found in the manifest and in Check 1's guidelines |
| Project-scoped Skills | `<project>/.claude/skills/` `<project>/skills-lock.json` | What is installed; diff against the capabilities the stack and phase call for. Look capabilities up in the user's skill catalog (if they keep one) before searching with `find-skills` |
| Hooks | `.claude/hooks/` and `hooks` in `settings.json` | Repeated manual steps or operations that must be blocked are wired |
| Remote Execution | `.claude/` session-start scaffold, `environment-setup.sh` | Only when the project is meant to run in a cloud environment |
| Toolchain | `.eslintrc*` `eslint.config.*` `ruff.toml` `pyproject.toml` `.golangci.yml` `clippy.toml` `.prettierrc*` `.editorconfig` `.gitattributes` `.github/workflows/*.yml` | Linter/Formatter configured for the detected language; formatter's linter-conflict rules disabled; test runner bound to a command; CI steps actually invoke lint/typecheck/test |

### Phase detection signals

| Signal | Command / Glob |
|--------|----------------|
| Repository age | `git rev-list --count HEAD` |
| Tests present | test file globs per language (see sections below) |
| CI configured | `.github/workflows/*.yml` `.gitlab-ci.yml` `Jenkinsfile` |
| Deploy configured | `vercel.json` `wrangler.toml` `Dockerfile` `fly.toml` `app.yaml` |
| Released before | `git tag` non-empty, or `gh release list` |

An explicit statement from the user always wins over these signals.

## Go

| Check | Glob | Grep Pattern |
|-------|------|-------------|
| Logging | `**/*.go` | `log/slog|logrus|zap|zerolog` |
| Error swallowed | `**/*.go` | `_ = .*err|_ =.*\.Close` |
| Config | `**/*.go` | `os\.Getenv|viper|envconfig|yaml\.Unmarshal` |
| Graceful shutdown | `**/*.go` | `signal\.Notify|signal\.NotifyContext` |
| Tests | `**/*_test.go` | (existence check) |
| Lock file | `go.sum` | (existence + `git ls-files go.sum`) |
| Migrations | `**/migrate*` `**/migration*` | `golang-migrate|goose|atlas` |
| API error responses | `**/*.go` | `http\.Error|ErrorResponse|WriteJSON.*err|status\.Internal` |
| Security | `**/*.go` | `cors\.|middleware\.Auth|\.Prepare\(|\.QueryRow\(` |

## JavaScript / TypeScript

| Check | Glob | Grep Pattern |
|-------|------|-------------|
| Logging | `**/*.{js,ts}` | `winston|pino|bunyan|log4js|consola` |
| Error swallowed | `**/*.{js,ts}` | `catch\s*\(\s*\w*\s*\)\s*\{\s*\}` |
| Config | `**/*.{js,ts}` | `dotenv|process\.env|config\.get` |
| Graceful shutdown | `**/*.{js,ts}` | `process\.on\(.*SIGTERM|process\.on\(.*SIGINT` |
| Tests | `**/*.{test,spec}.{js,ts}` `**/__tests__/**` | (existence check) |
| Lock file | `package-lock.json` `yarn.lock` `pnpm-lock.yaml` `bun.lockb` | (existence + `git ls-files`) |
| Migrations | `**/migrations/**` `**/migrate/**` | `knex|sequelize|prisma|typeorm|drizzle` |
| API error responses | `**/*.{js,ts}` | `res\.status\(4|res\.status\(5|AppError|HttpException|createError` |
| Security | `**/*.{js,ts}` | `cors\(|helmet\(|passport\.|jwt\.verify|parameterized|prepared` |

## Python

| Check | Glob | Grep Pattern |
|-------|------|-------------|
| Logging | `**/*.py` | `import logging|loguru|structlog` |
| Error swallowed | `**/*.py` | `except.*:\s*pass|except.*:\s*\.\.\.` |
| Config | `**/*.py` | `os\.environ|dotenv|pydantic.*Settings|configparser` |
| Graceful shutdown | `**/*.py` | `signal\.signal|atexit\.register` |
| Tests | `**/test_*.py` `**/*_test.py` | (existence check) |
| Lock file | `poetry.lock` `Pipfile.lock` `uv.lock` | (existence + `git ls-files`) |
| Migrations | `**/migrations/**` `**/alembic/**` | `alembic|django.*migrations|flask-migrate` |
| API error responses | `**/*.py` | `HTTPException|abort\(4|abort\(5|JsonResponse.*status` |
| Security | `**/*.py` | `CORSMiddleware|login_required|authenticate|%s.*SELECT` |

Note: `requirements.txt` is a dependency declaration, NOT a lock file. Only `poetry.lock`, `Pipfile.lock`, `uv.lock` count.

## Rust

| Check | Glob | Grep Pattern |
|-------|------|-------------|
| Logging | `**/*.rs` | `tracing|log|env_logger|slog` |
| Error swallowed | `**/*.rs` | `\.unwrap\(\)|\.expect\(` |
| Config | `**/*.rs` | `std::env|config::Config|clap|dotenvy` |
| Graceful shutdown | `**/*.rs` | `tokio::signal|ctrlc|signal_hook` |
| Tests | `**/*.rs` | `#\[test\]|#\[tokio::test\]` |
| Lock file | `Cargo.lock` | (existence + `git ls-files Cargo.lock`) |
| API error responses | `**/*.rs` | `StatusCode::|HttpResponse::.*Error|IntoResponse.*err` |
| Security | `**/*.rs` | `CorsLayer|tower_http::cors|sqlx::query` |

## Unsupported Languages

For languages not listed above (Java, Ruby, Swift, C#, Elixir, etc.), the AI should:
1. Detect the stack using the table below
2. Infer check patterns based on common libraries in that ecosystem
3. Mark all results with `[inferred]` to indicate no predefined pattern was used

## Detection: How to Identify the Stack

| File | Stack |
|------|-------|
| `go.mod` | Go |
| `package.json` | JavaScript/TypeScript |
| `pyproject.toml` `setup.py` `requirements.txt` | Python |
| `Cargo.toml` | Rust |
| `*.csproj` `*.sln` | C# / .NET |
| `build.gradle` `pom.xml` | Java / Kotlin |
| `Gemfile` | Ruby |
| `mix.exs` | Elixir |
| `Package.swift` | Swift |

## Detection: Components

| Signal | Component |
|--------|-----------|
| SQL driver imports, ORM imports, `.db` files, `DATABASE_URL` | Database |
| HTTP router/framework imports, listen/serve calls | HTTP API |
| CLI framework imports (cobra, click, clap, commander) | CLI |
| HTML templates, static file serving, frontend framework | Web UI |
| Message queue imports (amqp, kafka, nats, redis pub/sub) | Message Queue |
