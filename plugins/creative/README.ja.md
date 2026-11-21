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

## 設定

### ファイルの置き場

| 何か | 置き場 |
|---|---|
| motion-video のプロジェクト（`brief.md`・`music-brief.md`・`verify.md`・`video.js`・`out/`） | 指定したフォルダ、無ければ作業ディレクトリの `motion-video/<slug>/` |
| motion-video の作業用の PNG 連番と音声 | `os.tmpdir()/motion-video/`。自動では消えないので、動画ができたら消す |
| BGM 用のサウンドフォント | `~/.local/share/motion-video/soundfonts/`（自分で置く） |

プラグインのデータディレクトリには何も置かないので、アンインストールしてもこれらのファイルは消えない。

## 前提

- `motion-video` は Node.js・Chrome・ffmpeg
