#!/usr/bin/env python3
"""lint.py が使う denylist を生成する。具体的な名前はスキルに書かず、この環境から集める。

  python3 build_denylist.py [--out PATH] [--add-name 語 ...] [--add-host ホスト ...]

auto 節は毎回作り直す: $HOME とその末尾、$USER、git config user.name / user.email（とドメイン）、
gh api user の login と所属 org（gh が無い・未ログインなら skip）、hostname（.local 無しの短縮形も）。
manual 節は既存の内容を保持し、--add-name / --add-host で足す（手で編集してもよい）。
出力先の既定は ${XDG_CONFIG_HOME:-~/.config}/skill-lint/denylist.json。
プラグインのデータ領域（CLAUDE_PLUGIN_DATA）に置かないのは、manual 節が利用者の手書きで、
プラグインを外しても消えてほしくなく、入れ方（マーケットプレイス名）でパスが変わると困るため。
"""
import argparse, datetime, json, os, shutil, socket, subprocess

DEFAULT_OUT = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "skill-lint", "denylist.json")
MIN_AUTO_LEN = 3  # auto で拾う短すぎる語は誤爆するので入れない（manual は長さを問わない）
GENERIC_ACCOUNTS = {"root", "admin", "user", "ubuntu", "runner", "home", "vagrant", "ec2-user", "debian", "node", "app"}


def sh(*cmd):
    if not shutil.which(cmd[0]):
        return ""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def collect_auto():
    names, hosts, notes = set(), set(), []
    home = os.path.expanduser("~")
    names.update([home, os.path.basename(home)])
    if os.environ.get("USER"):
        names.add(os.environ["USER"])
    for key in ("user.name", "user.email"):
        # グローバルと実効値（リポのローカル設定が上書きしたもの）の両方を入れる
        for v in {sh("git", "config", "--global", key), sh("git", "config", key)}:
            if v:
                names.add(v)
                if "@" in v:
                    names.update([v.split("@")[0], v.split("@")[1]])
    login = sh("gh", "api", "user", "--jq", ".login")
    if login:
        names.add(login)
        names.update(x for x in sh("gh", "api", "user/orgs", "--jq", ".[].login").splitlines() if x)
    else:
        notes.append("gh が無いか未ログインのため gh の login / org は skip")
    hn = socket.gethostname()
    if hn:
        hosts.add(hn)
        hosts.add(hn.split(".")[0])
    # root・ubuntu など汎用のアカウント名は普通の文（project root 等）に当たるので入れない
    names = sorted(x for x in names if len(x) >= MIN_AUTO_LEN and x.lower() not in GENERIC_ACCOUNTS)
    hosts = sorted(x for x in hosts if len(x) >= MIN_AUTO_LEN)
    return {"names": names, "hosts": hosts, "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "notes": notes}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--add-name", nargs="*", default=[])
    ap.add_argument("--add-host", nargs="*", default=[])
    a = ap.parse_args()
    out = os.path.expanduser(a.out)
    manual = {"names": [], "hosts": []}
    if os.path.exists(out):
        manual.update(json.load(open(out, encoding="utf-8")).get("manual") or {})
    for key, add in (("names", a.add_name), ("hosts", a.add_host)):
        manual[key] = list(dict.fromkeys((manual.get(key) or []) + add))
    data = {"auto": collect_auto(), "manual": manual}
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=1)
        fp.write("\n")
    os.chmod(out, 0o600)
    print("書き出し: %s（auto 名前 %d・ホスト %d / manual 名前 %d・ホスト %d）" % (
        out, len(data["auto"]["names"]), len(data["auto"]["hosts"]), len(manual["names"]), len(manual["hosts"])))
    for n in data["auto"]["notes"]:
        print("  注: " + n)


if __name__ == "__main__":
    main()
