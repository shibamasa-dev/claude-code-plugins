# BGM の音源・インパルス応答の入れ方とライセンス

BGM（`meta.audio.music`）を使う動画にだけ要る。効果音だけの動画には要らない。
音源ファイルはスキルのリポジトリに置かず、スキルの外（`~/.local/share/motion-video/`）に置く。

## FluidSynth

```bash
brew install fluid-synth        # 2.6.1 で確認。LGPL-2.1
fluidsynth --version
```

render.mjs は `fluidsynth` を PATH から呼ぶ。無ければ `music` を指定した動画の storyboard / final がエラーで止まる（黙って BGM を抜かない）。

## サウンドフォント: GeneralUser GS（既定）

| 項目 | 値 |
|---|---|
| 版 | GeneralUser GS v2.0.3（License v2.0） |
| 作者 | S. Christian Collins（<https://www.schristiancollins.com/generaluser>） |
| 入手元 | <https://github.com/mrbumpy409/GeneralUser-GS>（作者の公式リポジトリ）の commit `684543d5e5efaef08d02be50dcda8d552478fa60` |
| 置き場 | `~/.local/share/motion-video/soundfonts/GeneralUser-GS.sf2`（ライセンス文を同じ場所に `GeneralUser-GS.LICENSE.txt` として置く） |
| sha256 | `9575028c7a1f589f5770fccc8cff2734566af40cd26ed836944e9a5152688cfe`（32,319,396 バイト） |

```bash
mkdir -p ~/.local/share/motion-video/soundfonts && cd ~/.local/share/motion-video/soundfonts
C=684543d5e5efaef08d02be50dcda8d552478fa60
curl -fL -o GeneralUser-GS.sf2 https://raw.githubusercontent.com/mrbumpy409/GeneralUser-GS/$C/GeneralUser-GS.sf2
curl -fL -o GeneralUser-GS.LICENSE.txt https://raw.githubusercontent.com/mrbumpy409/GeneralUser-GS/$C/documentation/LICENSE.txt
shasum -a 256 GeneralUser-GS.sf2   # 上の値と一致すること
```

ライセンスの要点（`GeneralUser-GS.LICENSE.txt` から）:

- 「You may use GeneralUser GS without restriction for your own music creation, private or commercial.」— 作った音楽（＝この動画の BGM）は私用・商用とも制限なく使える
- 収録サンプルについて「allow full use in music production, including the ability to make profit from musical recordings created with GeneralUser GS」
- ただし作者自身が「I cannot be 100% sure where all of the samples originated」と書いており、「This uncertainty may concern you if you intend to use GeneralUser GS in a commercial software product」と注意している。サウンドフォント自体をソフトウェア製品に同梱する用途では気にする必要がある（動画の BGM として書き出した音には上の1点目が当たる）
- 配布するときは作者のダウンロードファイルへ直接リンクしない（作者のサイトへリンクするか、自前の複製を置く）

別の音源に替えるときは `music.soundfont`（プロジェクトからの相対パス）か環境変数 `MOTION_VIDEO_SF2` で渡す。General MIDI 準拠の SF2 ならスタイルの楽器番号がそのまま効く。入れる前にライセンスを確かめて、この表に足す。

## インパルス応答（畳み込みリバーブ）

- **既定は合成**: `scripts/music.mjs` の `synthIR` が、シード固定の乱数から指数減衰するステレオのノイズを作る（高域ほど早く減衰させて部屋の吸音を近似）。ダウンロードもライセンスも要らず、毎回同じ波形になる。長さは `music.reverbSeconds`（既定 1.6 秒）
- **実測の IR を使うとき**: WAV を `music.ir`（プロジェクトからの相対パス）で渡す。置き場の目安は `~/.local/share/motion-video/ir/` かプロジェクトの中。ライセンスは IR ごとに違うので、入れる前に確かめてここに表を足す（候補: OpenAIR <https://www.openair.hosted.york.ac.uk/> の IR は多くが CC BY 系で、使うならクレジット表記が要る）

## 決定論について（2026-10-01 に実測）

- FluidSynth 2.6.1 の fast-render（`-F`）は、同じ MIDI・同じ SF2 なら毎回同じサンプル列を出す（内部のリバーブ・コーラスを入れても一致したが、スキルでは切っている）
- ただし FluidSynth が書く WAV は、ヘッダの PEAK チャンクに書き出し時刻が入るので **ファイルのハッシュは毎回変わる**。中身のサンプルは一致する。スキルはサンプルだけを ffmpeg で読むので mp4 には影響しない
- ffmpeg の `sidechaincompress` に別々のファイルを2つ入れると、終端でどちらが先に尽きるかで出力の長さが毎回変わった。スキルは効果音と BGM を1本の 4ch WAV にまとめてから分けて使う
