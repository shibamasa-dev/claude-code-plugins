#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.9"
# dependencies = ["pillow>=10"]
# ///
"""File work for the image history: make a compact proxy of a reference image under the plugin data directory.

    history.py proxy IMAGE [--max-edge 1280] [--quality 82] [--no-proxy]

Prints one JSON object with the values Claude records in img_references (source_path, source_sha256, source_bytes,
proxy_ref, proxy_bytes, width, height, max_edge, format). The database itself is reached through the plugin's MCP
server or a connector, never from here.

The proxy is a JPEG whose longer edge is at most --max-edge (never enlarged), with metadata stripped, saved as
<data>/image-history/references/<first 16 hex of the source's sha256>-<max edge>-q<quality>.jpg: the same source with
the same options gives the same file, and other options give another file instead of replacing it.
--no-proxy only hashes and measures the source and writes nothing (for a reference kept as notes only).

<data> is $CLAUDE_PLUGIN_DATA, used only when it names this plugin's own directory (`creative-<marketplace>` or
`creative-inline`): a command run through Bash may carry another plugin's value. SKILL.md puts the right value in
front of the command. Run it with `uv run --script` (it brings Pillow).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path


def plugin_data() -> Path:
    data = os.environ.get("CLAUDE_PLUGIN_DATA", "").strip()
    name = os.path.basename(os.path.normpath(data)) if data else ""
    if not data or data.startswith("${") or not (name == "creative" or name.startswith("creative-")):
        raise SystemExit(
            "CLAUDE_PLUGIN_DATA does not name the creative plugin's data directory "
            f"(got {data!r}). Run the command exactly as SKILL.md writes it."
        )
    return Path(data)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def make_proxy(src: Path, dest: Path, max_edge: int, quality: int) -> tuple:
    from PIL import Image, ImageOps  # imported here so the module loads on a python3 without Pillow

    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
            rgba = im.convert("RGBA")
            flat = Image.new("RGB", rgba.size, (255, 255, 255))  # JPEG has no alpha: put transparency on white
            flat.paste(rgba, mask=rgba.getchannel("A"))
            im = flat
        else:
            im = im.convert("RGB")
        im.thumbnail((max_edge, max_edge))  # shrinks only, keeps the aspect ratio
        dest.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(dest.parent), suffix=".part")
        os.close(fd)
        try:
            im.save(tmp, "JPEG", quality=quality, optimize=True)  # no exif= : metadata is dropped
            os.replace(tmp, dest)
        except BaseException:
            os.unlink(tmp)
            raise
        return im.size


def proxy(args: argparse.Namespace) -> dict:
    src = Path(args.image).expanduser().resolve()
    if not src.is_file():
        raise SystemExit(f"reference image not found: {src}")
    data = plugin_data()
    digest = sha256_file(src)
    out = {
        "source_path": str(src),
        "source_sha256": digest,
        "source_bytes": src.stat().st_size,
        "proxy_ref": None,
        "proxy_bytes": None,
        "width": None,
        "height": None,
        "max_edge": args.max_edge,
        "format": None,
    }
    if args.no_proxy:
        return out
    # The encoding options are part of the name, so a proxy made with other options never replaces one that rows
    # already point at (their width, height and size describe that file)
    name = f"{digest[:16]}-{args.max_edge}-q{args.quality}.jpg"
    dest = data / "image-history" / "references" / name
    width, height = make_proxy(src, dest, args.max_edge, args.quality)
    out.update(proxy_ref=name, proxy_bytes=dest.stat().st_size, width=width, height=height, format="jpg",
               proxy_path=str(dest))
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="File work for the creative plugin's image history.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("proxy", help="Make a compact JPEG proxy of a reference image and print its values.")
    p.add_argument("image")
    p.add_argument("--max-edge", type=int, default=1280)
    p.add_argument("--quality", type=int, default=82)
    p.add_argument("--no-proxy", action="store_true", help="Only hash and measure the source; write nothing.")
    args = parser.parse_args(argv)
    if args.max_edge <= 0 or not 1 <= args.quality <= 95:
        parser.error("--max-edge must be positive and --quality between 1 and 95")
    print(json.dumps(proxy(args), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
