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
| `image-generation-prompt` | ページ・スライド・文書の質が上がるときに画像アセットを提案し、承認を得てから生成する。指示文は設定した経路（Codex・Gemini API・OpenAI Image API・fal.ai）向けに構造化する |
| `motion-video` | 商品の画像・スクショ・ロゴ・実写クリップを載せたモーショングラフィックス動画を、コードで描いて書き出す |

`DESIGN.md` の lint は `lint` プラグインに移った。使い続けるなら `/plugin install lint@shibamasa-plugins` を実行する。

## 設定

| キー | 既定値 | 意味 |
|---|---|---|
| `image_routes` | 空 | 画像で試す経路の ID をカンマ区切りで先頭から順に: `codex`・`gemini`・`openai`・`fal`（例: `codex,gemini`）。空なら Claude が聞き、答えを保存するか尋ねる |
| `video_routes` | 空 | 動画で試す経路の ID を同じ形で: `gemini`・`fal` |

`/plugin` で設定するか、`echo '{"image_routes":"codex,gemini"}' | claude plugin configure creative@shibamasa-plugins --values-stdin` を実行してから `/reload-plugins` を実行する。経路ごとの呼び方は `skills/image-generation-prompt/references/routes.md` にある。

### ファイルの置き場

| 何か | 置き場 |
|---|---|
| motion-video のプロジェクト（`brief.md`・`music-brief.md`・`verify.md`・`video.js`・`out/`） | 指定したフォルダ、無ければ作業ディレクトリの `motion-video/<slug>/` |
| motion-video の作業用の PNG 連番と音声 | `os.tmpdir()/motion-video/`。自動では消えないので、動画ができたら消す |
| 生成した画像 | 成果物のフォルダ（例: `assets/`）。経路には絶対パスで保存先を渡す |
| BGM 用のサウンドフォント | `~/.local/share/motion-video/soundfonts/`（自分で置く） |

プラグインのデータディレクトリには何も置かないので、アンインストールしてもこれらのファイルは消えない。

## 前提

- `image-generation-prompt` は使う経路: サインイン済みの Codex CLI（`codex`）か、環境変数の API キー（`GEMINI_API_KEY`・`OPENAI_API_KEY`・`FAL_KEY`）
- `motion-video` は Node.js・Chrome・ffmpeg
