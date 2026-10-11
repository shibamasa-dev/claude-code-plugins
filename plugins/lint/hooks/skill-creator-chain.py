#!/usr/bin/env python3
"""Hook for PostToolUse (Skill) and UserPromptExpansion (typing /skill-creator directly): when skill-creator is used, tell Claude to run skill-lint on the finished skill.

Returns additionalContext only for skill-creator (including namespaced names like `skill-creator:skill-creator`);
prints nothing for any other skill. Keeps no state.
Never crashes on an exception; always exits 0.
"""
import json, sys

MESSAGE = ("[lint] skill-creator is in use. When you finish creating or updating the skill, run "
           "skill-lint on that skill's directory (/lint:skill-lint <skill directory>). "
           "Project-scoped skills (.claude/skills inside a repo) are out of scope.")


def main():
    if "--expansion" in sys.argv:  # UserPromptExpansion (the user typed /skill-creator): already narrowed by the matcher. Plain stdout goes into context
        print(MESSAGE)
        return
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
    except Exception as e:  # a hook must never crash
        print("skill-creator-chain: %s" % e, file=sys.stderr)
    sys.exit(0)
