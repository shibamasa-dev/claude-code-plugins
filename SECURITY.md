# セキュリティ

guards のフックをすり抜ける手順や、フック・スクリプトの脆弱性を見つけたら、公開の issue には書かず、GitHub の [Report a vulnerability](https://github.com/shibamasa-dev/claude-code-plugins/security/advisories/new) から非公開で知らせてほしい。

## 対象

- main の最新版
- `plugins/*/hooks/`・`plugins/*/bin/`・`plugins/*/skills/*/scripts/` のコード
- `.github/workflows/` と `.githooks/`

guards は Claude の誤操作を減らすための安全網で、悪意のある操作を止めるサンドボックスではない。サンドボックスとして使えないこと自体は脆弱性として扱わない。
