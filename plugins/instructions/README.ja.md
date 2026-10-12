# instructions

[English](README.md) | 日本語

プラグインに同梱した指示ファイルを、自分の `~/.claude/CLAUDE.md` と同じ扱いで Claude Code に読み込ませる mod です。CLAUDE.md をマシンごとにコピーしなくても、同じ作業ルールがどのマシンでも効きます。

## 導入

```text
/plugin marketplace add shibamasa-dev/claude-code-plugins
/plugin install instructions@shibamasa-plugins
```

## 指示ファイル

| ファイル | 内容 |
|---|---|
| `instructions/communication.md` | ユーザーの言語で簡潔に答える。ユーザーが目で確かめるファイル（PDF・画像・帳票・図面）はクリックできる相対パスのリンクで示し、ファイル名の `(` `)` はエスケープする。ユーザーが別のデバイスから見ているときはファイルそのものを送る |

## mod

| Mod | 内容 |
|---|---|
| `register.ts` | `prompt.context` で、上のファイルを `user` 種の指示ファイルとして足す。位置は自分の `~/.claude/CLAUDE.md` と rules の後、プロジェクトの `CLAUDE.md` の前。Claude Code は `~/.claude/CLAUDE.md` と同じ場所・同じ書式で見せ、`~/.claude/CLAUDE.md` を渡さない subagent（Explore・Plan など CLAUDE.md を省くもの）にはこのファイルも渡さない |

文脈は会話ごとに 1 回、`/clear` や compact の後にもう 1 回作られます。ファイルを書き換えたら、その次の作り直しから効きます。同じパスのファイルがすでに指示ファイルに入っていれば、二重には足しません。別の mod が CLAUDE.md の本文を書き換えていた場合は、元のファイルが分からないので何も足しません。

## 制限

- **Claude Code の組み込みガードが動く環境では効きません。** managed settings がある Mac、または Team / Enterprise のプランでサインインしているときは、Claude Code が組み込みのガード `sec-default@builtin` を入れます。このガードは、自分で入れたプラグインの `prompt.context` フックを飛ばします。会話には何も表示されず、debug ログに `prompt.context bypassed by cc-plugin-sec-default (tier user)` と出ます。これを変えられるのは managed settings だけです。managed settings の `prependPlugins` に `sec-default@builtin` を書かなければガードは入りませんが、自分で入れたプラグインに対するガードのほかの保護も外れます（[Manage mods for your organization](https://code.claude.com/docs/en/plugins/mods/admin) を参照）。
- ファイルは英語です。Claude はユーザーの言語で答えます。

## 前提

ターミナルなら Claude Code v2.1.287 以降、Desktop アプリの Code タブなら v2.1.286 以降（この版から mod が既定で有効）

## テスト

```bash
claude plugin test plugins/instructions
```
