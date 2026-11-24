#!/bin/bash
# Acceptance checks for hooks/now-context.py: runs the real hook with different CLAUDE_PLUGIN_OPTION_TIMEZONE values.
set -u
HOOK="$(cd "$(dirname "$0")/.." && pwd)/hooks/now-context.py"
ERR=$(mktemp "${TMPDIR:-/tmp}/now-context-err.XXXX")
trap 'rm -f "$ERR"' EXIT
run() { echo '{"hook_event_name":"UserPromptSubmit","prompt":"hi"}' | CLAUDE_PLUGIN_OPTION_TIMEZONE="$1" python3 "$HOOK" 2>"$ERR"; }

echo '=== timezone=UTC ==='
OUT=$(run UTC); CODE=$?
[ "$(printf '%s\n' "$OUT" | wc -l | tr -d ' ')" = 1 ] && r=ok || r=ng; echo "  lines -> $r (expect ok: exactly one line)"
printf '%s' "$OUT" | grep -Eq '^\[now\] [0-9]{4}-[0-9]{2}-[0-9]{2} \((Mon|Tue|Wed|Thu|Fri|Sat|Sun)\) [0-9]{2}:[0-9]{2} UTC$' && r=ok || r=ng
echo "  format '$OUT' -> $r (expect ok)"
# compare with date -u taken right after (retry once if the minute rolled over between the two)
want=$(date -u '+%Y-%m-%d %H'); got=$(printf '%s' "$OUT" | sed -E 's/^\[now\] ([0-9-]+) \([A-Za-z]+\) ([0-9]{2}):.*/\1 \2/')
[ "$got" != "$want" ] && { OUT=$(run UTC); want=$(date -u '+%Y-%m-%d %H'); got=$(printf '%s' "$OUT" | sed -E 's/^\[now\] ([0-9-]+) \([A-Za-z]+\) ([0-9]{2}):.*/\1 \2/'); }
[ "$got" = "$want" ] && r=ok || r=ng; echo "  date and hour '$got' vs date -u '$want' -> $r (expect ok)"
[ "$CODE" = 0 ] && r=ok || r=ng; echo "  exit $CODE -> $r (expect ok)"

echo '=== timezone empty: the system time zone ==='
OUT=$(run ""); CODE=$?
want=$(date '+%Y-%m-%d %H'); got=$(printf '%s' "$OUT" | sed -E 's/^\[now\] ([0-9-]+) \([A-Za-z]+\) ([0-9]{2}):.*/\1 \2/')
[ "$got" != "$want" ] && { OUT=$(run ""); want=$(date '+%Y-%m-%d %H'); got=$(printf '%s' "$OUT" | sed -E 's/^\[now\] ([0-9-]+) \([A-Za-z]+\) ([0-9]{2}):.*/\1 \2/'); }
[ "$got" = "$want" ] && r=ok || r=ng; echo "  date and hour '$got' vs date '$want' -> $r (expect ok)"
[ "$CODE" = 0 ] && r=ok || r=ng; echo "  exit $CODE -> $r (expect ok)"

echo '=== timezone Asia/Tokyo: the zone name is shown ==='
OUT=$(run Asia/Tokyo)
want=$(TZ=Asia/Tokyo date '+%Y-%m-%d %H'); got=$(printf '%s' "$OUT" | sed -E 's/^\[now\] ([0-9-]+) \([A-Za-z]+\) ([0-9]{2}):.*/\1 \2/')
[ "$got" != "$want" ] && { OUT=$(run Asia/Tokyo); want=$(TZ=Asia/Tokyo date '+%Y-%m-%d %H'); got=$(printf '%s' "$OUT" | sed -E 's/^\[now\] ([0-9-]+) \([A-Za-z]+\) ([0-9]{2}):.*/\1 \2/'); }
[ "$got" = "$want" ] && r=ok || r=ng; echo "  date and hour '$got' vs TZ=Asia/Tokyo date '$want' -> $r (expect ok)"
case "$OUT" in *' JST') r=ok ;; *) r=ng ;; esac; echo "  '$OUT' ends in JST -> $r (expect ok)"

echo '=== invalid timezone ==='
OUT=$(run Not/AZone); CODE=$?
[ "$CODE" = 0 ] && r=ok || r=ng; echo "  exit $CODE -> $r (expect ok)"
[ "$(printf '%s\n' "$OUT" | wc -l | tr -d ' ')" = 1 ] && printf '%s' "$OUT" | grep -q '^\[now\] ' && r=ok || r=ng
echo "  still one [now] line -> $r (expect ok)"
[ -s "$ERR" ] && r=ok || r=ng; echo "  a note on stderr -> $r (expect ok)"
