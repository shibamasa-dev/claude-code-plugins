## 何が変わるか

<!-- 利用者から見て何が変わるか。Before / After で書くと伝わりやすい -->

## 関連 issue

<!-- 次の2行を必ず書く（review プラグインの dev-flow スキルの約束）
     Closes #N（受け入れ基準をすべて満たす）か Refs #N（一部だけ）。issue が無い依頼なら Refs: none (verbal request)
     Arch-Review: not-needed — <理由>　か　Arch-Review: approved — <GO の在りか> -->

Refs #
Arch-Review: not-needed — 

## 確認したこと

- [ ] 中身を変えたプラグインの `version` を上げ、`CHANGELOG.md` に同じ版の見出しを足した
- [ ] `claude plugin validate --strict` が通る
- [ ] フックを変えたら `plugins/<plugin>/tests/run-all.sh` が通る
- [ ] 個人のパス・メールアドレス・社内の固有名が入っていない（`python3 .github/scripts/check-repo.py`）
