---
name: motion-video
description: 商品の画像・スクショ・ロゴ・実写クリップを載せたモーショングラフィックス動画（紹介動画・製品デモ・SNS 用の縦短尺・ループ）を、コードで1コマずつ描いて mp4 に書き出す。HTML/Canvas の seek(t) レンダラをエージェントが書き、ヘッドレス Chrome で 60fps の連番にして ffmpeg で H.264 にする。音は拍に乗せた効果音と、コード進行からコードで作曲して FluidSynth で鳴らす BGM。雑メモか指示書 → 難所の技術検証 → カット表（カットごとに はじめ/おわり の2コマ＋FB 欄）で人と版を回す → 人の OK → 本番書き出し → 9:16 / 1:1 / 16:9 の順で進める。「動画を作って」「紹介動画」「プロモ動画」「モーショングラフィックス」「モーションデザイン」「アニメーション動画」「ロゴアニメ」「縦動画」「リール / ショート用」「スクショを動かして見せたい」「mp4 で書き出して」「絵コンテ」「カット表」「動画に BGM を付けて」で必ず使う。生成 AI の実写動画・ナレーション音声は扱わず、画像生成 API も呼ばない（必要な画像の一覧を出し、人が外で作った画像を素材として受け取る）。
---

# motion-video

動画を「時刻 t を渡すとその瞬間の1コマを描く関数」として書き、それを 1 コマずつ撮って mp4 にする。
生成 AI の動画と違い、**同じ入力なら毎回同じ mp4**（ハッシュ一致）になり、気になる1コマだけを直せて、追加費用もかからない。

- 実行本体: `scripts/render.mjs`（依存ゼロ。node 22+（グローバル WebSocket を使う）/ Google Chrome か Chromium / ffmpeg）。音は `scripts/audio.mjs`（効果音・混ぜ合わせ・仕上げ）と `scripts/music.mjs`（BGM の作曲と演奏）
- 書き方の正典: `references/authoring.md`（video.js の契約・API・画角の組み直し・音・ループ）
- BGM の音源・インパルス応答の入れ方とライセンス: `references/audio-assets.md`
- 入口（雑メモ・指示書ひな形）: `references/brief-template.md` / 音楽ブリーフ: `references/music-brief.md` / 自己採点: `references/self-review.md`
- ブランド設定の例: `references/brand.example.json`

## 前提

- **Chrome は Claude Code の Bash sandbox 内では起動しない**（mach bootstrap が拒否される）。`render.mjs` と `evals/run.sh` は `dangerouslyDisableSandbox: true` で実行する。
- sandbox の内と外で `$TMPDIR` が違う。パスは絶対パスで渡す。作業用の連番 PNG は `os.tmpdir()/motion-video/` に置かれる。
- Chrome が標準の場所に無ければ `MOTION_VIDEO_CHROME=<実行ファイル>` を渡す。
- BGM（`meta.audio.music`）を使うときだけ FluidSynth（`brew install fluid-synth`）とサウンドフォント（既定 `~/.local/share/motion-video/soundfonts/GeneralUser-GS.sf2`）が要る。無ければエラーで止まる。入れ方は `references/audio-assets.md`。
- プロジェクト（video.js・素材・書き出し）はスキルの外に置く（作業中のリポジトリの `tmp/` など）。スキルのリポジトリに動画・画像を置かない。

以下 `R=${CLAUDE_PLUGIN_ROOT}/skills/motion-video/scripts/render.mjs`。

## 手順

### ① 入口: 雑メモか指示書

`references/brief-template.md` の入口を選ぶ。
**既定は「雑メモで始める」**: 人には 印象・シーンごとの雑なメモ・素材一覧 だけを頼み、エージェントがカット割り（最初のカット表）と音楽ブリーフ（`references/music-brief.md`。BGM を付けるとき）を先に提案して、人が直す。白紙のひな形を渡すと人の手が止まる。
添える指示の型: 「アイデアはヒント。再現を目指さない。表現は過剰でよい」。
人が指示書を書きたいなら、ひな形を `brief.md` として写して埋める。決まっていない項目だけを質問で埋める（1回に3問まで。順番はひな形の末尾）。

**素材一覧を先に確定する**。製品の UI・数字・主張は、実物が無ければ作らずに人へ求める（捏造した画面や数字で動画を作らない）。
素材の権利（使ってよい写真・ロゴか）の判定はこのスキルの範囲外。人に確かめる。
テクスチャ・実写素材が要るなら **素材の請求表**（分類 / ストックの ID か検索語 / 内容 / 使いどころ）を、コードで描くと平たくなる素材（看板・ラベル類）が要るなら **必要な画像の一覧**（枚数・サイズ・用途・5セクション構造のプロンプト）を出して人に渡す（`references/authoring.md` の 13・14）。ダウンロード・生成・権利の判断は人がする。

### ② 難しいシーンは技術検証してから

実写クリップを多く使う・合成が重い・描画が重い（粒子が多い・テクスチャを何枚も重ねる）シーンは、v1 の前にそのシーンだけ試作する。
試作は本番と同じ `video.js` の形で書き、`node $R stills <project> --times <秒,…>` で描いて Read で見る。描画時間は stills の実行時間を枚数で割る（Chrome の起動を均すため 10 枚以上描く）。
結果を `verify.md` にシーンごとに書く:

```markdown
| シーン | 判定 | 何をどう作るか | 要るもの | 1コマの描画時間 |
|---|---|---|---|---|
| s3 | ● 目処が立った | 実写クリップ3本を springTrack で入れ替え | clips/a.mp4 ほか | 0.18 秒 |
| s5 | ▲ リスクあり（対策あり） | ヒビのテクスチャを screen で重ねる。輪郭に模様 → alpha 0.2 に | assets/tex/crack.jpg（請求中） | 0.31 秒 |
| s6 | ○ 未検証 | 破片 300 枚 | — | — |
```

▲・○ が残る・描画時間が重すぎる（本番は 尺×fps×サブフレーム4 枚描く）なら、**結果を見て構成を変えてよい**（カットを割る・質感を削る・尺を詰める）。変えたら人に伝える。
同じ記号でシーンの `verify` 欄に要点を書くと、カット表の検証欄に出る。

### ③ カット表を起こす

1. `references/authoring.md` を読んで `video.js` を書く。`meta.scenes` がそのままカット表になる（1シーン＝1カット。伝えること・画面・動き・テキスト・音・つなぎ・検証）。ブランドは brand.json から読み、色を直書きしない。
2. 絵コンテを書き出す:
   ```bash
   node $R storyboard <project> --aspect all
   ```
   主な出力は `out/storyboard/cutsheet.html`（**カット表**。1行＝1カット、画は「はじめ」「おわり」の2コマ、開始と尺は秒と拍、検証欄、黄色い FB 欄）。ほかに `storyboard.md`（シーン表と警告）と、画角ごとに次が出る:
   - `cuts/<カット>-start.png` / `-end.png`（カット表の2コマ）と、シーンごとの代表コマ
   - `contact.png`（1拍に1コマ）/ `strip.png`（いちばん速い動きの前後12コマ）/ `phone.png`（スマホ幅 390px に縮めたもの）/ `seam.png`（ループ作品だけ）
   - `beats.json`（拍・小節頭・ピーク）
   - 音がある動画は `audio/`: `preview.wav`（本番と同じ手順で混ぜた音）/ `spectrogram.png`（白線=シーンの境目・緑線=ピーク）/ `audio.json`（LUFS・トゥルーピーク・帯域ごとの RMS）/ `bgm.mid`（BGM があるとき）
   - 決定論チェック（同じコマを2回描いてハッシュ比較）の結果
3. **警告を全部片付ける**（シーン契約の空欄・ハードカット・4秒以上変化が無い区間・拍から外れた効果音・フォント不在・決定論チェック失敗・対応が書かれていない FB）。直せない警告は、人に見せるときに理由を添える。

### ④ 自己採点 → カット表で FB を往復 → 人の OK

`references/self-review.md` の9項目（フック・スマホでの読みやすさ・動きの質・視覚の変化・構図・ブランドの正確さ・音の同期・ありがち度・緩急）を、**出た PNG を Read で実際に見て** 1〜10 で採点する。
最悪の3件をタイムスタンプ付きで挙げて直し、該当の秒だけ描き直して確かめる（`node $R stills <project> --from 4.0 --to 4.5`）。全項目 8 点以上になるまで繰り返す。

音がある動画は `audio/spectrogram.png` も Read で見て、曲の山が緑線（ピーク）に来ているか・効果音と BGM が同じ帯域でぶつかっていないかを確かめ、`audio.json` の帯域ごとの RMS で低域のこもりを見る（low が lowmid より大きければこもり気味。スペクトログラムの最下段は対数軸でにじむので数字で判断する）。

そのうえで cutsheet.html・点数と、音があれば `audio/preview.wav` を人に見せて聴いてもらい、**ここで必ず止まる**。人がその場にいないなら、待つ（勝手に承認しない）。

人の返事は2通り:

- **FB**: 人はカット表の FB 欄に書き、「FB を保存」で `feedback/v<N>.json` をプロジェクトに置く（形は `references/authoring.md` の「12. カット表と FB の往復」）。エージェントは FB ごとに直し、**同じファイルの `response` に対応を、`summary` にこの版で変えたことを書いてから** storyboard を回す。版が v<N+1> に進み、前の版は `out/storyboard/v<N>/` に残り、カット表の冒頭に「v<N> の FB への対応」表と、FB の付いたカットの新旧比較画像が出る。対応の書き漏れは警告になる。自己採点からやり直して、また見せて止まる
- **OK**: その発言を記録して承認する:

```bash
node $R approve <project> --by "<OK を出した人>" --note "<OK の発言そのまま>"
```

`approve` は、今のソース（video.js・素材・brand.json・feedback/）のハッシュと、絵コンテを作った時のハッシュが一致するときだけ通る。

### ⑤ 本番を書き出す

```bash
node $R final <project>            # meta.aspects の全画角
node $R final <project> --aspect 9:16
```

- 承認が無い、または承認後にソースが1バイトでも変わっていると exit 3 で止まる。直したら ③ からやり直してもう一度 OK をもらう（この仕組みがあるので、承認後に黙って直して出すことはできない）。
- 書き出し前に決定論チェックを再度通す。60fps（meta.fps）・サブフレーム4枚のモーションブラー・H.264 / yuv420p / CRF 16・音声 AAC 192kbps。音（効果音だけでも BGM つきでも）は -14 LUFS ±1・トゥルーピーク -1 dBFS 以下に仕上げ、mp4 を ebur128 で測り直した値を README と manifest に書く。
- 納品物は `out/deliver/`: 画角ごとの `final.mp4` / `poster.png` / `contact.png`、`source/`（ソース一式と approval.json）、`README.md`、`manifest.json`（ハッシュ・probe・ラウドネス・BGM の記録（スタイル・音源の sha256・MIDI の sha256）・描いた素材）。

書き出した後にもう一度自己採点する（poster.png と contact.png を Read で見る）。直すところがあれば ③ に戻る。
仕上がりを人に渡すときは mp4 と poster をクリックで開けるリンクで示す。

### ⑥ 画角を揃える

**9:16 を先に作り**、同じタイムライン（同じ video.js）から 1:1・16:9 を組み直す。横のマスターを切り抜かない。
組み直しは固定ピクセルでなくレイアウト関数（`ctx.L` の `u` / `safe` / `split` / `grid` / `orient`）で行う。`meta.aspects: ['9:16', '1:1', '16:9']` にして storyboard `--aspect all` で全画角のコマを確かめてから承認をもらう。

## その他のコマンド

| コマンド | 用途 |
|---|---|
| `node $R check <project> [--frame 300]` | 同じコマを「最初に描いた時」と「他のコマの後」で比べる。ループなら継ぎ目の連続性も |
| `node $R stills <project> --times 1.2,3.4` / `--from a --to b` | 該当の秒だけ描き直す（`out/stills/<画角>/`） |
| `node $R probe <file.mp4>` | 解像度・fps・コマ数・尺・音声・sha256 |
| `node scripts/audio.mjs --duration 6 --cues cues.json [--music music.json --scenes scenes.json --peaks 4] --out x.wav [--spectrogram x.png]` | 音だけを本番と同じ手順で作って試聴（Chrome 不要・sandbox 内で動く） |
| `node scripts/music.mjs --duration 8 --bpm 120 --progression Am,F,C,G --style calm --out bgm.wav` / `--styles` | BGM だけ（エフェクト前）を鳴らす / スタイルの一覧 |

## 扱わないもの

- 生成 AI の実写動画（Gemini 等）・生成 AI の作曲・有料のナレーション音声・外部 API の呼び出し全般（ストック素材の検索・ダウンロードも含む）
- スキルからの画像生成 API の呼び出し。必要な画像の一覧（プロンプト付き）を出すところまでがスキルの仕事で、生成は人の承認後にスキルの外で行い、できた画像を素材として受け取る
- 素材の権利判定・ダウンロード（素材の請求表を出し、人が判断して置く）
- three.js / WebGL の 3D・写真からの深度推定・体験型 Web サイト化
- DOM / CSS アニメーション（canvas に描いたものだけが写る）

## 限界

- ハッシュ一致は「同じマシン・同じ Chrome・同じ ffmpeg・同じ FluidSynth とサウンドフォント」の範囲。どれかを上げるとコマの画素や音が変わりうる。サウンドフォントはプロジェクトの外にあるので承認のハッシュに入らない（manifest に sha256 を残す）。
- BGM は2スタイル（calm / upbeat）の決まった編曲の型で、メロディは書かない。曲の良し悪しは preview.wav を人が聴いて決める。ループ作品に BGM を付けると、最後のフェードで継ぎ目に音の落ち込みが出る。
- フォントは brand.json で `fonts.*.file` を渡さない限りシステムにあるものを使う。無ければ fallback で描き、storyboard が警告する。
- 長い実写クリップは全コマをメモリに載せる。`meta.clips.*.maxWidth` と fps で抑える。

## eval

```bash
sh ${CLAUDE_PLUGIN_ROOT}/skills/motion-video/evals/run.sh            # sandbox 外で。数分かかる
sh ${CLAUDE_PLUGIN_ROOT}/skills/motion-video/evals/run.sh --only media-mix-image-and-clip-30fps
```

`evals/evals.json` の6ケース（架空の Example Co. 紹介 15 秒 16:9 / 画像＋実写クリップ 30fps / 9:16・1:1・16:9 のループ / BGM つき 8 秒 / カット表と FB の往復（v1→v2） / 契約の否定ケース）を実際に書き出して機械判定し、`pass_rate` と、ケースごとの `grading/<name>.json`（skill-creator の grading 形式: text / passed / evidence）を出す。生成物は `--work`（既定 `os.tmpdir()`）へ出る。
