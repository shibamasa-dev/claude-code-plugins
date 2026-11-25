# Test fixtures

## Official forms (unmodified)

| File | Source | Fetched | sha256 |
|---|---|---|---|
| `cfa-standard.xlsx` | 「就労証明書（標準的な様式）（Excel）」, https://www.cfa.go.jp/policies/hoiku/shugyoshomeisho | 2026-11-24 | `cd73f518e477d062d0eb1c8434224ae4b9340add233c68894a3e76156621a7fd` |
| `cfa-simple.xlsx` | 「別添 就労証明書（簡易版）標準的な様式（令和5年5月29日付け事務連絡）（Excel）」, same page | 2026-11-24 | `71e3dc7884533622fdce7b61d6bfe2b6924ea4a15061d56882d49db309097b9e` |

出典：「就労証明書」（こども家庭庁）（https://www.cfa.go.jp/policies/hoiku/shugyoshomeisho）. Content of the Children and Families Agency site is provided under the Public Data License 1.0 (PDL1.0, https://www.cfa.go.jp/copyright-policy). The files are kept byte for byte as published; the tests write filled copies to a temporary directory and never change them.

The simplified form ships with the Monday to Friday checkboxes of item 6 already ticked (`☑`); the tests rely on that.

## Synthetic data

`last-year-simple.xlsx` stands in for "last year's certificate": `cfa-simple.xlsx` with the synthetic values of `spec-lastyear.json` written by `certfill.py fill`, checked by rendering it with LibreOffice. The tests check its cells against the raw sheet XML, not through `certfill.py`. Credit for this edited copy: 「就労証明書（簡易版）標準的な様式」（こども家庭庁）（https://www.cfa.go.jp/policies/hoiku/shugyoshomeisho）を加工して作成 (filled in with synthetic values by the hr plugin's tests).

Everything under `company/` and every value in `spec-*.json` is **synthetic**: invented names, a fictional address and an all-zero phone number, made up for the tests. No real company, person, child or municipality. A real filled case (with personal values replaced) will replace or join them when one is available.
