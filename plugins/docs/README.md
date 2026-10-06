# docs

画像と動画を作るときのスキル。

## スキル

| スキル | 使いどころ |
|---|---|
| `image-generation-prompt` | 画像生成の指示文を構造化する。生成経路（Gemini API・OpenAI Image API・fal.ai など）に依存しない |
| `motion-video` | 商品の画像・スクショ・ロゴ・実写クリップを載せたモーショングラフィックス動画を、コードで描いて書き出す |

## フック

| フック | いつ | 何をするか |
|---|---|---|
| design-lint | Edit・Write の後 | `DESIGN.md` を編集したら `npx @google/design.md lint` を走らせ、指摘を返す。ほかのファイルでは何もしない |

## 前提

- `motion-video` は Node.js・Chrome・ffmpeg
- `design-lint` は `npx`（ネット接続が要る）
