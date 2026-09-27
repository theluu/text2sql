#!/usr/bin/env bash
# Redeploy the current HEAD to the production server (native: systemd + host nginx/Postgres/Redis).
# First-time server setup (DBs, roles, pg_hba, .env, TLS) is described in deploy/README.md.
set -euo pipefail
HOST=${DEPLOY_HOST:-root@45.118.145.203}
APP=/opt/text2sql/app
WEB=/var/www/text2sql.themeshub.net/public
ROOT=$(git rev-parse --show-toplevel)
SHA=$(git rev-parse HEAD)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
# One multiplexed SSH connection for scp + ssh: the server rate-limits new connections.
mkdir -p "$HOME/.ssh/cm"
SSH_OPTS=(-o ControlMaster=auto -o "ControlPath=$HOME/.ssh/cm/%r@%h:%p" -o ControlPersist=10m -o ConnectTimeout=20)

cd "$ROOT"
[ -z "$(git status --porcelain -- backend frontend)" ] || { echo "backend/ or frontend/ has uncommitted changes" >&2; exit 1; }
(cd frontend && npm run build >/dev/null)
git archive --format=tar.gz -o "$TMP/backend.tar.gz" HEAD backend
COPYFILE_DISABLE=1 tar -czf "$TMP/web.tar.gz" -C frontend/dist .
scp -q "${SSH_OPTS[@]}" "$TMP/backend.tar.gz" "$TMP/web.tar.gz" "$HOST:/tmp/"

ssh "${SSH_OPTS[@]}" "$HOST" bash -s -- "$SHA" <<'REMOTE'
set -euo pipefail
SHA=$1
APP=/opt/text2sql/app
WEB=/var/www/text2sql.themeshub.net/public
# Code only: .env and .venv live next to it and are left untouched.
tar -xzf /tmp/backend.tar.gz -C "$APP" && chown -R text2sql:text2sql "$APP"
cd "$APP/backend"
sudo -u text2sql -H env UV_PYTHON_INSTALL_DIR=/opt/text2sql/.python UV_CACHE_DIR=/opt/text2sql/.cache/uv \
  uv sync --frozen --no-dev --python 3.12 -q
sudo -u text2sql .venv/bin/python -m app.cli bootstrap 2>&1 | grep -iE "error|hardening_skipped" || true   # idempotent: migrations + eval cases
# Function-level revokes need the superuser (t2s_admin is not one).
(cd /tmp && sudo -u postgres psql -q -v ON_ERROR_STOP=1 -d t2s_warehouse < "$APP/backend/app/warehouse/schema/04_hardening.sql")
sed -i "s/^Environment=GIT_SHA=.*/Environment=GIT_SHA=$SHA/" /etc/systemd/system/text2sql-api.service /etc/systemd/system/text2sql-worker.service
systemctl daemon-reload
systemctl restart text2sql-api text2sql-worker
rm -rf "$WEB.new" && mkdir -p "$WEB.new" && tar -xzf /tmp/web.tar.gz -C "$WEB.new"
rm -rf "$WEB.old" && mv "$WEB" "$WEB.old" && mv "$WEB.new" "$WEB" && rm -rf "$WEB.old"
for i in $(seq 1 30); do curl -fsS 127.0.0.1:8021/api/health >/dev/null 2>&1 && break; sleep 1; done
curl -fsS 127.0.0.1:8021/api/health && echo
REMOTE
echo "deployed $SHA → https://text2sql.themeshub.net"
