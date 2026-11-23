#!/bin/bash
# Search with the form SKILL.md teaches: search_text LIKE '%' || img_norm('<term>') || '%' ESCAPE '\'
# Terms come from the skill's eval prompts (Japanese requests), run against attempts from a real history.
set -u
. "$(dirname "$0")/lib.sh"

# hits TERM [ROLE]: the titles found, comma-separated, newest first. With ROLE, only attempts that have a reference with it
hits() {
  local t=${1//\'/\'\'} role=""
  [ -n "${2:-}" ] && role="AND reference_roles LIKE '%$2%'"
  sql "SELECT title FROM img_v_attempts WHERE search_text LIKE '%' || img_norm('$t') || '%' ESCAPE '\\' $role ORDER BY id DESC" |
    python3 -c 'import json,sys; print(",".join(r[0] for r in json.load(sys.stdin)["rows"]))'
}

fresh_db
load_fixtures

# "前に作ったレイド告知っぽい構図で…": the earlier raid banner is found by the word from its prompt
row 'half-width ﾚｲﾄﾞ finds the attempt whose prompt has レイド' "$(yesno [ "$(hits 'ﾚｲﾄﾞ')" = 'Original mecha announcement banner v2' ])" 'yes'
row 'upper-case MECHA finds both mecha banners' "$(yesno [ "$(hits 'MECHA')" = 'Original mecha announcement banner v2,Mecha raid announcement banner' ])" 'yes'
row 'full-width ｌｅｆｔ－ｃｕｔｉｎ finds the tag' "$(yesno [ "$(hits 'ｌｅｆｔ－ｃｕｔｉｎ')" = 'Original mecha announcement banner v2,Mecha raid announcement banner' ])" 'yes'
# "テイストと画風だけ使って…": only attempts with a style_only reference
row 'banner with role style_only' "$(yesno [ "$(hits 'banner' style_only)" = 'Original mecha announcement banner v2,Mecha raid announcement banner' ])" 'yes'
row 'banner with role composition_only finds only the first' "$(yesno [ "$(hits 'banner' composition_only)" = 'Mecha raid announcement banner' ])" 'yes'
row 'the Japanese requests with 告知バナー are found' "$(yesno [ "$(hits '告知バナー')" = 'Original mecha announcement banner v2,Mecha raid announcement banner' ])" 'yes'
# "サイバーパンクなSaaSのヒーロー画像": nothing similar yet
row 'サイバーパンク finds nothing' "$(yesno [ "$(hits 'サイバーパンク')" = '' ])" 'yes'
row 'a quote in the term is embedded safely and finds nothing' "$(yesno [ "$(hits "o'clock")" = '' ])" 'yes'
row 'the refinement points at the attempt it builds on' "$(yesno [ "$(val "SELECT b.title FROM img_attempts a JOIN img_attempts b ON b.id = a.based_on WHERE a.title = 'Original mecha announcement banner v2'")" = 'Mecha raid announcement banner' ])" 'yes'
