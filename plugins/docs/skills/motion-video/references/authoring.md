# video.js の書き方（レンダー契約と API）

目次: 1. プロジェクトの形 / 2. meta / 3. render(ctx, t) の契約 / 4. ctx / 5. 動きの部品（ctx.M） / 6. 描画の部品（ctx.D） / 7. 画角ごとの組み直し / 8. 素材・クリップ・フォント / 9. 音 / 10. ループ / 11. 見た目の既定 / 12. カット表と FB の往復 / 13. 実写テクスチャを重ねる / 14. 生成画像を素材として受け入れる

## 1. プロジェクトの形

```
<project>/
├── brief.md          指示書か雑メモ（references/brief-template.md）
├── music-brief.md    音楽ブリーフ（BGM を付けるとき。references/music-brief.md）
├── verify.md         技術検証メモ（難しいシーンがあるとき。SKILL.md の手順②）
├── video.js          meta と render(ctx, t) を export する（これを書く）
├── brand.json        色・書体・ロゴ（無ければ --brand で外から渡す。例: references/brand.example.json）
├── assets/           画像（PNG / JPG / SVG / WebP）
├── clips/            実写クリップ（mp4 等。ffmpeg が読めれば何でも）
├── feedback/         v<N>.json = 版 N への人の FB とエージェントの対応（12.）
├── approval.json     approve コマンドが書く（手で作らない）
└── out/              書き出し先（storyboard/ stills/ deliver/）
```

置き場所はスキルの外（作業中のプロジェクトの `tmp/` など）。スキルのリポジトリに動画・画像を置かない。

## 2. meta

```js
export const meta = {
  title: 'Example Co. 紹介',
  duration: 15,            // 秒。duration × fps が整数になるように
  fps: 60,                 // 既定 60
  aspects: ['9:16', '1:1', '16:9'],  // 先頭が主画角（絵コンテの既定）。9:16 を先に作る
  loop: false,             // ループ作品なら true（継ぎ目の連続性を検査する）
  poster: 13.8,            // poster.png にする時刻（省略時は最後のシーンの代表コマ）
  subframes: 4,            // モーションブラーのサブフレーム数（既定 4）
  shutter: 0.5,            // シャッター角（1コマの何割の時間を混ぜるか。既定 0.5 = 180°）
  assets: { shot: 'assets/dashboard.png' },            // ctx.img('shot')
  clips: { demo: { src: 'clips/demo.mp4', fps: 30, maxWidth: 1280 } },  // ctx.clip('demo', 秒)
  scenes: [ /* シーン契約。下記 */ ],
  audio: { bpm: 120, offset: 0, beatsPerBar: 4, peaks: [0, 12], cues: [ /* 9. 音 */ ] },
};
```

### シーン契約（scenes の各要素）

```js
{
  id: 's2', start: 3, end: 6,       // 秒。隙間・重なりなく 0 から duration まで並べる
  key: 4.8,                          // 代表コマの時刻（省略時は中央）。複数なら keys: [3.6, 5.2]
  message: '伝えること（1文）',
  screen: '画面: 構図・物・カメラ',
  motion: { enter: '入場', main: '主動作', secondary: '副動作', exit: '退場' },  // 文字列でもよい
  narration: 'ナレーション1文（音声は作らない。字幕や読み上げ原稿として使う）',
  text: '画面に出す文字（省略時はカット表のテキスト欄に narration を出す）',
  sound: '音',
  transition: '画面上の物が次のシーンの物にどう変わるか',  // 「カット」は警告になる
  energy: 0.8,                       // 省略可。BGM の層の厚さ 0..1（省略時はピーク・最初・最後のシーンかで決まる。9. 音）
  verify: ['● 面の変形は springTrack で目処', '▲ 9:16 で右カードが安全域に食い込む（縮めて対処予定）'],  // 省略可。カット表の検証欄（12.）
}
```

storyboard はこの欄をそのままシーン表とカット表（1シーン＝1カット）にする。空欄・隙間・ハードカットは警告に出る（`text`・`verify` は空でも警告しない）。

## 3. render(ctx, t) の契約

`render(ctx, t)` は **時刻 t だけで1コマが決まる純関数**（seek(t)）。フレーム 812 は 0〜811 を描かずに正しく描ける。

- 禁止: 前フレームからの持ち越し（モジュール変数に位置を足していく等）/ タイマー・requestAnimationFrame / CSS transition・DOM アニメーション（canvas 以外は写らない）/ `Math.random`・`Date.now`・`performance.now`（描画中は例外で止まる）
- 乱数は `ctx.M.rng(seed)` をその場で作って使う（毎コマ同じ seed から引く）
- 毎コマ、harness が canvas を消して変換・透明度を戻してから呼ぶ。背景は自分で塗る
- `check` コマンドが「同じコマを最初に描いた時」と「他のコマを描いた後」を比べ、違えば失敗にする
- async にしてもよい（素材は事前に全部読み込み済みなので、普通は同期で足りる）

## 4. ctx

| 名前 | 中身 |
|---|---|
| `g` | CanvasRenderingContext2D |
| `W`, `H` | 画角のピクセル（16:9=1920x1080 / 9:16=1080x1920 / 1:1=1080x1080 / 4:5=1080x1350） |
| `L` | レイアウト（7.） |
| `M` / `D` | 動きの部品 / 描画の部品 |
| `brand` | brand.json の中身（`brand.colors.primary` など） |
| `meta`, `fps`, `duration` | meta の値 |
| `beats` | `M.beatGrid(meta.audio.bpm, …)` |
| `font(role, size, weight=700)` | brand.fonts[role] の CSS font 文字列（fallback 込み） |
| `img(key)` | 素材の画像。`'@logo'` は brand.json の logo |
| `clip(key, 秒, { loop })` | クリップの その秒のコマ（画像） |
| `scene(t)` | t のシーン `{ id, start, end, local, p }`（p = シーン内の進捗 0..1） |
| `text(str, x, y, opts)` | 文字（折り返し・禁則つき）。opts: font, color, align, baseline, maxWidth, lineHeight, letterSpacing, alpha |
| `image(img, box, opts)` | 画像を枠へ（opts: fit 'contain'/'cover', radius, alpha） |

## 5. 動きの部品（ctx.M）

- `spring(t, preset)` — 0→1 のばね（closed-form・数式で解いた厳密解）。t<=0 は 0
  - `snappy`（k260/d24・ボタン・トグル）/ `default`（k170/d26・カード・カメラ・文字）/ `playful`（k130/d18・マスコット）/ `heavy`（k120/d30/m2.5・大きな面。スキル独自の推測値）
  - UI は小さく行き過ぎてよい（snappy / playful）。**文字は行き過ぎさせない**（default / heavy）
- `springTrack(t, keys, preset)` — ターゲットが変わるたびにばねを1本足す。`keys = [{t:0,v:0},{t:1.2,v:100},{t:3,v:40,preset:'snappy'}]`。途中で行き先が変わっても値も速度も連続する
- `springDuration(preset)` — 収束までの秒数（シーン尺の見積もり）
- `progress(t, a, b)`（0..1 に正規化）/ `ease.outCubic` ほか / `lerp` / `clamp` / `stagger(start, i, gap)`
- `beatGrid(bpm).beat(n)` / `.bar(n, b)` / `.nearest(t)` — 拍・小節頭の時刻
- `rng(seed)` / `mixColor(a, b, p)` / `withAlpha(hex, a)`

文字と容器の順番（プレイブックの型）:

```js
const out = M.ease.inCubic(M.progress(t, end - 0.45, end - 0.2)); // 文字は変形より先に退場
const box = M.springTrack(t, [{ t: 0, v: A }, { t: end - 0.15, v: B }]);  // 容器の変形は境界の少し前から
const inn = M.spring(t - (end + 0.15), 'default');                  // 新しい文字は変形が始まってから
```

## 6. 描画の部品（ctx.D）

`D.fill(g, W, H, color)` / `D.roundRect(g, x, y, w, h, r)`（パスを作るだけ。fill/stroke/clip は自分で）/ `D.text(g, …)` / `D.image(g, …)` / `D.wrapLines(g, text, maxWidth)`

## 7. 画角ごとの組み直し

固定ピクセルで置かない。`L = layout(W, H)` の単位で置く:

- `L.u` — 短辺の 1%。文字サイズ・余白・角丸はこれの倍数（`6 * L.u` など）
- `L.orient` — `'landscape' | 'portrait' | 'square'`。並べ方の分岐に使う
- `L.safe` — 端から 6% 内側の安全域 `{x, y, w, h}`。文字はこの中に置く
- `L.split(gap)` — 横長なら左右、縦長なら上下の2分割
- `L.grid(cols, rows, gap, box)` — 格子のセル
- `M.fit(iw, ih, box, 'contain'|'cover')`

9:16 を先に組み、同じ関数が 1:1 と 16:9 でも破綻しないか storyboard `--aspect all` で見る。横のマスターを切り抜かない。

## 8. 素材・クリップ・フォント

- 画像: `meta.assets` に登録 → `ctx.img(key)`。全部読み込み終えてから 1コマ目を描くので、読み込み待ちは要らない
- SVG は `width` / `height` 属性を必ず書く（無いと Chrome で 300x150 などになる）
- 実写クリップ: **ブラウザの `<video>` は使わない**。render.mjs が ffmpeg で `meta.clips.*.fps` の連番にばらしてキャッシュし、`ctx.clip(key, 秒)` がその秒のコマを返す。長い素材は `maxWidth` で縮める（全コマをメモリに載せる）
- フォント: brand.json の `fonts.<role>.file` にフォントファイル（brand.json からの相対パス。可変フォント可）を渡すと @font-face で読み込む。無ければ family 名でシステムから探し、無ければ fallback で描く（storyboard が警告を出す）
- 素材の権利（使ってよい写真・ロゴか）の判定はこのスキルの範囲外。指示書の素材一覧で人が確認する

## 9. 音

音は「効果音（cues）」と「BGM（music）」の2層。どちらも無ければ無音の mp4、`music` が無ければ効果音だけで動く（FluidSynth もサウンドフォントも要らない）。

```js
audio: {
  bpm: 120, offset: 0, beatsPerBar: 4,
  peaks: [0, 12],                       // 主役の登場（小節頭に置く）。BGM の山もここに合わせる
  cues: [
    { bar: 0, sfx: 'thump' },           // 小節頭
    { beat: 6, sfx: 'whoosh', gain: 0.6 },
    { t: 3.5, sfx: 'pop', pan: -0.3 },
    { t: 3.62, sfx: 'click', offbeat: true },  // 拍から外すときは明示
  ],
  music: {                              // 省略すると効果音だけ
    progression: ['Am', 'F', 'C', 'G'], // コード進行（繰り返す）
    style: 'calm',                      // calm / upbeat
    chordBars: 1,                       // 1つのコードを何小節鳴らすか（0.5 で1小節に2つ）
    seed: 1,                            // 強弱とタイミングの揺らぎの乱数（変えると別テイク）
    humanize: 1,                        // 揺らぎの量（0 で揺らさない）
    gainDb: 0,                          // 効果音に対する BGM の大きさ（+ で BGM を上げる）
    duck: 5,                            // 効果音が鳴る瞬間に BGM を下げる強さ（サイドチェーンの圧縮比。1 で下げない）
    reverb: 0.3,                        // リバーブの混ぜ具合（0..1）
    reverbSeconds: 1.6,                 // 合成インパルス応答の長さ
    // ir: 'ir/hall.wav',               // 実測のインパルス応答を使うとき（プロジェクトからの相対パス）
    // soundfont: 'sf/other.sf2',       // 音源を変えるとき（既定は下記）
  },
}
```

### 効果音

`click / pop / thump / whoosh`（scripts/audio.mjs でコード合成・シード固定）。拍から外れた cue・小節頭から外れたピークは storyboard が警告する。

### BGM（作曲 → 演奏）

- **作曲**（scripts/music.mjs）: 拍の格子（bpm・offset・beatsPerBar）の上に、コード進行とスタイルから MIDI（SMF）をコードで書く。生成 AI は使わない
- **スタイル**
  - `calm`: パッド（GM 89 Warm Pad）＋ピアノのアルペジオ（GM 0）＋ベース（GM 32）。ドラムなし。energy が低いと4分・高いと8分、山の小節は1オクターブ上を混ぜる
  - `upbeat`: ドラム（ch10）＋ベースの8分（GM 33）＋エレピの裏拍の刻み（GM 4）＋薄いパッド。山の前の小節にスネアのフィル、山の小節頭にクラッシュ
  - 両方とも、山の前の小節でパッドを膨らませ（CC11）、最後の小節は和音を尺の最後まで伸ばす
- **展開はシーン表から**: 小節ごとの energy（0..1）を、そのシーンの `energy` 欄（書けば優先）か既定（ピークを含むシーン 1.0 / 最初 0.45 / 最後 0.7 / その他 0.65）で決め、層を出し入れする。映像の山（`peaks`）と曲の山が同じ小節に来る
- **揺らぎ**: `seed` 固定の乱数で、音の強さを ±8・タイミングを拍の ±2% 揺らす（パッドの和音・小節頭のキック・山のクラッシュ・曲頭の1拍目はタイミングを揺らさず、強さだけ揺らす）
- **演奏**: FluidSynth がサウンドフォント（既定 `~/.local/share/motion-video/soundfonts/GeneralUser-GS.sf2`。`music.soundfont` → 環境変数 `MOTION_VIDEO_SF2` → 既定の順で探す）を 48kHz・32bit float で鳴らす。FluidSynth 内部のリバーブ・コーラスは切る（響きは ffmpeg 側で付ける）。入れ方とライセンスは `references/audio-assets.md`
- 同じ MIDI・同じ音源・同じ FluidSynth の版なら、演奏した WAV を作業フォルダでキャッシュする

### 混ぜ方と仕上げ（final と storyboard で同じ手順）

1. BGM: 50Hz 以下を切る → 250Hz を -3dB → 3kHz を -2dB（効果音の帯域を空ける）→ 軽いコンプ → 畳み込みリバーブ（`afir`。インパルス応答は既定でシード固定の合成、`music.ir` で実測のものに差し替え）→ ステレオを広げる（`stereowiden`）→ 最後の 0.5 秒をフェード
2. BGM を -20 LUFS（＋`gainDb`）に揃え、効果音が鳴る瞬間だけ BGM を下げて（`sidechaincompress`）混ぜる
3. 全体のゲインを決め、4倍オーバーサンプリングしたリミッター（`alimiter`・天井 -2 dBFS）でピークを抑える。実測して -14 LUFS ±0.2 に入るまでゲインを詰める
4. 納品と同じ設定（AAC 192kbps）で符号化して測り、トゥルーピークが -1 dBFS を超えていればリミッターの天井を下げてやり直す

結果は -14 LUFS ±1・トゥルーピーク -1 dBFS 以下（効果音だけの動画も同じ。まばらな効果音だけだとリミッターで強く潰して届かせるので、preview.wav で聴いて確かめる）。
BGM は最後の 0.5 秒でフェードアウトするので、ループ作品（`meta.loop: true`）に BGM を付けると継ぎ目で音が一度下がる。final は mp4 の音声を ebur128 で測り直して README と manifest に書く。

### 絵コンテで聴く・見る

storyboard は `out/storyboard/audio/` に次を出す（音がある動画だけ）:

- `preview.wav` — 本番と同じ手順で混ぜた音。人に絵コンテを見せるとき一緒に渡して聴いてもらう
- `spectrogram.png` — 周波数を対数軸にしたスペクトログラム。白線がシーンの境目、緑線がピーク。**Read で見て**、曲の山がピークに来ているか・効果音と BGM が同じ帯域でぶつかっていないかを確かめる
- `audio.json` — 音量（LUFS）・トゥルーピーク（WAV と AAC 後）・ラウドネスレンジ・帯域ごとの RMS（sub <40Hz / low 40–120 / lowmid 120–500 / mid 500–4k / high >4k）。スペクトログラムの最下段は対数軸でにじんで実際より明るく見えるので、低域のこもりは帯域ごとの RMS で判断する（low が lowmid より大きければこもり気味）
- `bgm.mid` — 作曲した MIDI（DAW で開いて確かめられる）

単体で試す（Chrome が要らないので sandbox 内で動く）:

```bash
node scripts/audio.mjs --duration 8 --bpm 120 --cues cues.json --music music.json --scenes scenes.json --peaks 4 --out /tmp/mix.wav --spectrogram /tmp/spec.png
node scripts/music.mjs --duration 8 --bpm 120 --progression Am,F,C,G --style upbeat --out /tmp/bgm.wav   # BGM だけ（エフェクト前）
node scripts/music.mjs --styles
```

## 10. ループ

`meta.loop: true` にすると、check と storyboard が「最後のコマ→最初のコマの変化量」を「隣り合うコマの変化量」と比べる。位置だけでなく速度もつながっていないと失敗する。
動きは `Math.sin(2π t / duration)` のような周期関数で書く。`t % duration` で包むだけでは直らない（継ぎ目で跳ぶのは同じ）。

## 11. 見た目の既定

- 禁止: グラデーション背景の上に中央タイトル / 全部フェードイン / 隅のラベル / 枠線 / グロー
- 2〜4 秒ごとに新しい視覚イベント（storyboard が「目立つ変化が無い区間」を警告する）
- トランジションは画面上の物が次のシーンの物に変わる形（面が縮んで柱になる・カードが次のカードになる）

## 12. カット表と FB の往復

`storyboard` は `out/storyboard/cutsheet.html`（静的 HTML。画像は相対パス）を出す。1行＝1カット（＝1シーン）で、画は「はじめ」（そのカットの最初のコマ `start`）と「おわり」（最後のコマ `end - 1/fps`）の2コマ、動きは文章。

- 冒頭: `CUT SHEET v<N>`・前の版の FB ファイルの `summary`（この版で変えたこと）・チップ（BPM / 小節数 = 秒 / カット数 / 解像度·fps / 素材の点数）・警告
- プロジェクト情報: プロジェクト名 / 全体の尺 / テンポ・BPM / 画面比 / 納品物 / 参考（`meta.reference`）/ カラー・フォント（brand.json）
- タイムライン帯: 1マス＝1小節、シーンを色帯で、その下にカット番号
- 「v<N-1> の FB への対応」表（版 2 以降）: 対象 / FB / 対応 / カット（比較画像）
- カット表の列: No. / 開始（秒・拍）/ 尺 / はじめ / おわり /（画角が複数なら 他の画角）/ 画の内容（message＋screen）/ 動き / 次へのつなぎ / テキスト / 音 / 検証（`verify`）/ FB（黄色い入力欄）
- 開始と尺は秒と拍の両方（`beats.json` と同じ bpm・offset・beatsPerBar から。例 120 BPM で 9.5 秒 = 小節5 拍4（19拍））

画像は `out/storyboard/<画角>/cuts/<カット ID>-start.png` / `-end.png`。

### 検証欄（エージェントが書く）

シーンの `verify`（文字列の配列か、改行区切りの文字列）。行頭の記号で色が付く:

- `●` できたこと・目処が立った / `▲` リスク・未解決（対策を書く）/ `◆` 素材・次の予定 / `✓` 確認済み / `○` 未検証

### FB ファイル

人は版 N のカット表を見て、`feedback/v<N>.json` を書く（カット表の「FB を保存」で、FB 欄に書いた内容がこの形で保存される）:

```json
{
  "cuts": {
    "s2": "カードが入るのが早い。1拍遅らせて",
    "s4": { "fb": "数字をもっと大きく", "response": "数字を 1.4 倍にした" }
  },
  "overall": "全体にもう少し余白がほしい",
  "summary": "（エージェントが書く）次の版で変えたことの1段落"
}
```

- キーはカット ID（シーンの `id`）。値は文字列（FB だけ）か `{ fb, response }`、複数なら配列。`overall` は全体への FB
- **エージェントは同じファイルに対応を書く**: 文字列の FB を `{ "fb": "…", "response": "…" }` に直し、`summary` に版の要約を書く
- 版番号は「FB ファイルのある最新の版 + 1」（FB が無ければ v1）。FB の無い再実行では版は進まず、同じ版を作り直す
- `storyboard` は最新の版を `out/storyboard/` 直下に作り、同じものを `out/storyboard/v<N>/` に残す。前の版の `v<N-1>/` は消さない（v1 と v9 を並べて比べられる）
- 版 2 以降は、FB の付いたカットについて前の版と今の版の はじめ / おわり を並べた比較画像（上段=前の版・下段=今の版）を `out/storyboard/compare/<カット ID>-v<N-1>-v<N>.png` に出す
- 警告: 対応（`response`）が書かれていない FB / 今のシーン表に無いカット ID への FB / 前の版のコマが無くて比較を作れない

`feedback/` はプロジェクトの中なので**承認のハッシュに入る**。FB を足したのに storyboard を回していなければ `approve` が「ソースが変わっている」で止まる（FB を反映しないまま承認できない）。対応を書いたら storyboard を回し直してから見せる。

FB の裏付けが要るとき（「ここがカクつく」等）は、該当区間を細かく描いて新旧を並べる: `node <skill>/scripts/render.mjs stills <project> --from 13.3 --to 15.0` を版ごとに回し、`out/stills/<画角>/sheet.png` を比べる。

## 13. 実写テクスチャを重ねる

全部をコードで描くと「CG っぽいきれいさ」になる。実写のテクスチャを薄く重ねて手触りを出す。

| 分類 | 例 | 使いどころ | 合成 |
|---|---|---|---|
| ガラスのヒビ | 割れたガラスの写真（黒地に白いヒビ） | 衝撃・転換の1カットだけ | `screen`（白いヒビだけが乗る） |
| リソグラフの粒・版ズレ | リソ印刷のスキャン、2色の版ズレ | 面・大きな文字に紙の手触り | `multiply`（粒が面を汚す）。版ズレは同じ面を 1〜2px ずらしてもう1色 |
| 網点 | 印刷の網点の拡大 | 写真素材・グラデーションの代わり | `multiply` か `overlay` |
| ガラスの拭き跡・指紋 | 窓ガラスの汚れ（黒地） | 画面越し・レンズ越しの感じ | `screen`、alpha 0.1〜0.3 |
| ブラウン管の蛍光体 | CRT の RGB 蛍光体の接写 | 画面・UI を映すカット | `multiply` か `overlay`、拡大して縞を目立たせない |

合成の仕方（`meta.assets` に登録して `ctx.img`）:

```js
g.save();
g.globalCompositeOperation = 'multiply';   // screen / overlay / soft-light など
g.globalAlpha = 0.35;
ctx.image(ctx.img('riso'), { x: 0, y: 0, w: W, h: H }, { fit: 'cover' });
g.restore();
```

- 毎コマ同じ画を貼ると止まって見える。動かすなら位置・角度を `M.rng(seed)` で小節ごとに切り替える（コマごとの乱数は決定論を壊さないが、ちらつく）
- 合成モードはコマごとに harness が `source-over` に戻すが、`save` / `restore` で囲む
- **重ねた素材が輪郭まわりに模様を出すことがある**（レンズの汚れ系で起きやすい）。重ねたら該当の秒を `node <skill>/scripts/render.mjs stills <project> --from a --to b` で描き直して Read で見る。模様が出たら alpha を下げるか、その素材を外す
- 効いていない質感は足すより削る（`self-review.md` の「ありがち度」「緩急」）

### 素材の請求表

テクスチャ・実写素材はエージェントが**請求表**を出し、**ダウンロードと権利の判断は人**がする。スキルは外部 API を呼ばない（ストックサイトの検索・ダウンロードもしない）。

| 分類 | ストックの ID か検索語 | 内容 | 使いどころ（カット） | 置き場所 |
|---|---|---|---|---|
| リソグラフの粒 | `risograph grain texture` | 白地に粗い粒、A4 スキャン相当 | s1・s5 の面 | assets/tex/riso.jpg |
| ガラスの拭き跡 | `glass smudge black background` | 黒地に白い拭き跡 | s3 の画面越し | assets/tex/smudge.jpg |

人が置いたら `meta.assets` に足し、カット表の検証欄に `◆ riso.jpg 待ち` → `✓ riso.jpg 反映` のように書く。

## 14. 生成画像を素材として受け入れる

スキル自身は画像生成を呼ばない。コードで描くと平たくなる素材（看板・ラベル・パッケージ・手描きの小物など）は、**必要な画像の一覧**を出して人に渡す:

| キー | 枚数 | サイズ | 用途（カット） | プロンプト |
|---|---|---|---|---|
| sign | 1 | 1600×900・PNG・背景透過 | s2 の店頭看板 | 5セクション構造（下記） |

プロンプトは5セクション構造で書く（Scene / Subject / Important details / Use case / Constraints。Constraints を空にしない）。docs プラグインの `image-generation-prompt` スキルがあればそれで組む。

生成はスキルの外で、**人の承認を得てから**行う（codex など人が選んだ経路で）。できた画像は通常の素材と同じく `assets/` に置いて `meta.assets` に足す。製品の UI・数字・ロゴは生成しない（実物を人に求める）。
