#!/usr/bin/env bash
# Run before every push. Any output from the checks below means: stop.
set -u
cd "$(dirname "$0")/.."
fail=0
echo "1. pytest on a clean checkout of HEAD (parallel tracks may have unfinished files in the working tree)"
wt=$(mktemp -d)/head; git worktree add -q --detach "$wt" HEAD
(cd "$wt" && "$OLDPWD/.venv/bin/python" -m pytest -q -p no:cacheprovider) || fail=1
git worktree remove --force "$wt"
echo "2. style: em dash / emoji in tracked files (testset excluded)"
out=$(git grep -nP "\x{2014}|[\x{1F300}-\x{1FAFF}\x{2600}-\x{27BF}\x{1F000}-\x{1F2FF}\x{FE0F}]" HEAD -- . ':!testset'); [ -n "$out" ] && { echo "$out"; fail=1; }
echo "3. style: last commit message"
out=$(git log -1 --format=%B | .venv/bin/python -c "import re,sys; t=sys.stdin.read(); print('\\n'.join(re.findall(r'.*[\u2014\U0001F300-\U0001FAFF\u2600-\u27BF].*', t)))"); [ -n "$out" ] && { echo "$out"; fail=1; }
echo "4. secret scan (key formats with a minimum length; plain 'sk-' would match words like 'risk-margin')"
out=$(git grep -nE "(\bsk-[A-Za-z0-9_-]{20,}|csk-[A-Za-z0-9]{20,}|gsk_[A-Za-z0-9]{20,}|\bAC[a-f0-9]{32}\b|-----BEGI[N]|\b[0-9]{8,10}:[A-Za-z0-9_-]{30,})" HEAD -- .); [ -n "$out" ] && { echo "$out" | cut -c1-80; fail=1; }
echo "5. no co-author trailers"
out=$(git log --format=%B | grep -i co-authored); [ -n "$out" ] && { echo "$out"; fail=1; }
[ $fail -eq 0 ] && echo "PREPUSH OK" || { echo "PREPUSH FAILED"; exit 1; }
