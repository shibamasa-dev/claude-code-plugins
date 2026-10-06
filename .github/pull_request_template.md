## 何が変わるか

<!-- 利用者から見て何が変わるか。Before / After で書くと伝わりやすい -->

## 確認したこと

- [ ] 中身を変えたプラグインの `version` を上げ、`CHANGELOG.md` に同じ版の見出しを足した
- [ ] `claude plugin validate --strict` が通る
- [ ] フックを変えたら `plugins/<plugin>/tests/run-all.sh` が通る
- [ ] 個人のパス・メールアドレス・社内の固有名が入っていない（`python3 .github/scripts/check-repo.py`）
