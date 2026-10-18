#!/usr/bin/env bash
# Pull-based deploy: if origin/main has new commits, update the checkout, rebuild when the
# dependencies changed, restart the service, and roll back if the site does not come up.
# Run every 30 seconds by deploy/uniteideas-deploy.timer. Safe to run by hand.
set -uo pipefail

main() {
  cd "$(dirname "$0")/.." || exit 1
  local branch="${DEPLOY_BRANCH:-main}" port="${PORT:-8100}"
  local log=data/deploy.log
  mkdir -p data/backups
  say() { echo "$(date '+%F %T') $*" >> "$log"; }

  exec 9>data/.deploy.lock
  flock -n 9 || exit 0   # a deploy is already running

  git fetch -q origin "$branch" 2>>"$log" || exit 0   # offline or GitHub hiccup: try again next tick
  local old new
  old=$(git rev-parse HEAD)
  new=$(git rev-parse "origin/$branch")
  [[ "$old" == "$new" ]] && exit 0
  [[ -f data/.deploy.skip && "$(cat data/.deploy.skip)" == "$new" ]] && exit 0   # this commit already failed

  say "deploying ${old:0:7} -> ${new:0:7}"
  [[ -f data/uniteideas.db ]] && cp data/uniteideas.db "data/backups/uniteideas-$(date +%Y%m%d-%H%M%S).db"
  ls -1t data/backups/*.db 2>/dev/null | tail -n +21 | xargs -r rm -f

  local deps_changed=0
  git diff --name-only "$old" "$new" | grep -qE '^(pyproject.toml|uv.lock|requirements.*)$' && deps_changed=1
  git reset -q --hard "$new" >>"$log" 2>&1
  if [[ $deps_changed == 1 || ! -d .venv ]]; then ./build.sh >>"$log" 2>&1 || say "build failed"; fi

  systemctl --user restart uniteideas >>"$log" 2>&1
  for _ in $(seq 1 20); do
    sleep 1
    if curl -fsS "http://127.0.0.1:$port/api/health" >/dev/null 2>&1; then say "ok, now at ${new:0:7}"; exit 0; fi
  done

  say "site did not come up, rolling back to ${old:0:7}"
  git reset -q --hard "$old" >>"$log" 2>&1
  [[ $deps_changed == 1 ]] && ./build.sh >>"$log" 2>&1
  local last; last=$(ls -1t data/backups/*.db 2>/dev/null | head -1)
  [[ -n "$last" ]] && cp "$last" data/uniteideas.db
  systemctl --user restart uniteideas >>"$log" 2>&1
  # Remember the bad commit so we do not retry it every 30 seconds.
  echo "$new" > data/.deploy.skip
  exit 1
}

main "$@"; exit $?
