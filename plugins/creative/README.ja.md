# creative

[English](README.md) | 日本語

画像・動画を作るときのスキル。

## 導入

```text
/plugin marketplace add shibamasa-dev/claude-code-plugins
/plugin install creative@shibamasa-plugins
```

## スキル

| スキル | 使いどころ |
|---|---|
| `image-generation-prompt` | 画像生成の指示文を構造化する。生成経路（Gemini API・OpenAI Image API・fal.ai など）に依存しない |
| `motion-video` | 商品の画像・スクショ・ロゴ・実写クリップを載せたモーショングラフィックス動画を、コードで描いて書き出す |

`DESIGN.md` の lint は `lint` プラグインに移った。使い続けるなら `/plugin install lint@shibamasa-plugins` を実行する。

## 前提

- `motion-video` は Node.js・Chrome・ffmpeg
