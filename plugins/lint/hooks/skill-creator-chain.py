#!/usr/bin/env python3
"""PostToolUse（Skill）hook: skill-creator が呼ばれたら、作り終えたスキルに skill-lint を走らせるよう伝える。

skill-creator（`skill-creator:skill-creator` のような名前空間付きも含む）のときだけ additionalContext を返し、
ほかのスキルでは何も出さない。状態は持たない。
何が起きても例外で落ちず exit 0。
"""
import json, sys

MESSAGE = ("[lint] skill-creator を使っている。スキルの作成・更新が終わったら、そのスキルのディレクトリに "
           "skill-lint を走らせる（/lint:skill-lint <スキルのディレクトリ>）。"
           "プロジェクトスコープ（リポ内の .claude/skills）のスキルは対象外。")


def main():
    try:
        inp = json.load(sys.stdin)
    except Exception:
        return
    skill = str((inp.get("tool_input") or {}).get("skill", ""))
    if skill == "skill-creator" or skill.endswith(":skill-creator"):
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": MESSAGE}},
                         ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # hook は絶対に落とさない
        print("skill-creator-chain: %s" % e, file=sys.stderr)
    sys.exit(0)
