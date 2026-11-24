#!/bin/bash
# scripts/history.py proxy: the reference proxy goes under the plugin data directory and nowhere else.
# Sizes come from a real history: a 16:9 banner became a 1280x720 proxy, a 564x307 reference stayed 564x307.
# Needs uv (the script brings Pillow through `uv run --script`).
set -u
. "$(dirname "$0")/lib.sh"

proxy() { uv run --quiet --script "$HISTORY" proxy "$@"; }
field() { python3 -c 'import json,sys; v = json.load(sys.stdin)[sys.argv[1]]; print("NULL" if v is None else v)' "$1"; }

fresh_data
src=$(mktemp -d "${TMPDIR:-/tmp}/creative-src.XXXXXX")
uv run --quiet --with 'pillow>=10' python3 - "$src" <<'PY'
import sys
from PIL import Image
d = sys.argv[1]
Image.new("RGB", (1920, 1080), (200, 30, 30)).save(f"{d}/告知バナー 参考.png")
Image.new("RGB", (564, 307), (20, 20, 120)).save(f"{d}/small.png")
Image.new("RGBA", (800, 800), (0, 0, 0, 0)).save(f"{d}/transparent.png")
# An RGB PNG whose black is the transparent color (tRNS), and a JPEG carrying a comment
Image.new("RGB", (400, 300), (0, 0, 0)).save(f"{d}/trns.png", transparency=(0, 0, 0))
Image.new("RGB", (400, 300), (90, 90, 90)).save(f"{d}/with-comment.jpg", comment=b"source note: do not ship")
PY
before=$(ls "$src" | sort | tr '\n' ,)

out=$(proxy "$src/告知バナー 参考.png")
ref=$(field proxy_ref <<<"$out")
row 'a 1920x1080 source becomes a 1280x720 proxy' "$(field width <<<"$out")x$(field height <<<"$out")" '1280x720'
row 'the proxy is a JPEG in image-history/references under the data directory' "$(yesno [ -f "$CLAUDE_PLUGIN_DATA/image-history/references/$ref" ])" 'yes'
sha=$(python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$src/告知バナー 参考.png")
row 'source_sha256 is the sha256 of the Japanese-named source' "$(yesno [ "$(field source_sha256 <<<"$out")" = "$sha" ])" 'yes'
row 'the proxy file is named by the first 16 hex of the hash and the options' "$(yesno [ "$ref" = "${sha:0:16}-1280-q82.jpg" ])" 'yes'
filesha() { python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$1"; }
kept=$(filesha "$CLAUDE_PLUGIN_DATA/image-history/references/$ref")
small=$(proxy "$src/告知バナー 参考.png" --max-edge 512 | field proxy_ref)
row 'a proxy made with other options gets another file' "$(yesno [ "$small" != "$ref" ] && [ -f "$CLAUDE_PLUGIN_DATA/image-history/references/$small" ])" 'yes'
row 'the earlier proxy is left as it was' "$(yesno [ "$(filesha "$CLAUDE_PLUGIN_DATA/image-history/references/$ref")" = "$kept" ])" 'yes'
row 'proxy_bytes is the size of the file written' "$(yesno [ "$(field proxy_bytes <<<"$out")" = "$(wc -c <"$CLAUDE_PLUGIN_DATA/image-history/references/$ref" | tr -d ' ')" ])" 'yes'
row 'a 564x307 source is not enlarged' "$(proxy "$src/small.png" | python3 -c 'import json,sys; d = json.load(sys.stdin); print("%sx%s" % (d["width"], d["height"]))')" '564x307'
row 'a transparent PNG becomes a JPEG proxy' "$(proxy "$src/transparent.png" | field format)" 'jpg'
# look PATH...: the corner pixel of each proxy, and whether it still carries a JPEG comment
look() { uv run --quiet --with 'pillow>=10' python3 -c 'import sys
from PIL import Image
for p in sys.argv[1:]:
    with Image.open(p) as im:
        print(im.getpixel((0, 0)), "comment" in im.info)' "$@"; }
trns=$(proxy "$src/trns.png" | field proxy_path)
row 'the tRNS transparent color of an RGB PNG becomes white' "$(yesno grep -Eq '^\((25[0-5]), (25[0-5]), (25[0-5])\) ' <<<"$(look "$trns")")" 'yes'
commented=$(proxy "$src/with-comment.jpg" | field proxy_path)
row 'a JPEG comment in the source is not copied to the proxy' "$(look "$commented" | awk '{print $NF}')" 'False'
row 'the source folder is left as it was' "$(yesno [ "$(ls "$src" | sort | tr '\n' ,)" = "$before" ])" 'yes'

fresh_data
out=$(proxy "$src/small.png" --no-proxy)
row '--no-proxy reports the hash and size' "$(field source_bytes <<<"$out")" "$(wc -c <"$src/small.png" | tr -d ' ')"
row '--no-proxy writes nothing' "$(find "$CLAUDE_PLUGIN_DATA" -type f | wc -l | tr -d ' ')" '0'

other="$(dirname "$CLAUDE_PLUGIN_DATA")/inventory-shibamasa-plugins"
CLAUDE_PLUGIN_DATA="$other" proxy "$src/small.png" >/dev/null 2>&1; rc=$?
row "another plugin's CLAUDE_PLUGIN_DATA is refused" "$(yesno [ "$rc" != 0 ] && [ ! -e "$other" ])" 'yes'
env -u CLAUDE_PLUGIN_DATA uv run --quiet --script "$HISTORY" proxy "$src/small.png" >/dev/null 2>&1; rc=$?
row 'an unset CLAUDE_PLUGIN_DATA is refused' "$(yesno [ "$rc" != 0 ])" 'yes'
rm -rf "$src"
