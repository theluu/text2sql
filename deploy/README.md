# Production deploy — text2sql.themeshub.net

The production server is shared with other sites, so the app runs **natively**. It does not use Docker there.

| Piece | Where |
|---|---|
| API | systemd `text2sql-api` → uvicorn on `127.0.0.1:8021` (user `text2sql`, `MemoryMax=800M`) |
| Eval worker | systemd `text2sql-worker` → arq (`MemoryMax=600M`) |
| Code / venv / env | `/opt/text2sql/app/backend` (`.venv`, `.env` mode 600 owned by `text2sql`) |
| Frontend | static build in `/var/www/text2sql.themeshub.net/public` |
| Web + TLS | host nginx vhost `nginx-text2sql.themeshub.net.conf`, Let's Encrypt certificate via certbot webroot |
| Databases | host Postgres 14 + pgvector: `t2s_app`, `t2s_warehouse`, owner role `t2s_admin` |
| Redis | host Redis, database `5` |

## Redeploy

```bash
deploy/deploy.sh        # builds the frontend, ships HEAD, migrates, restarts, health-checks
```

## First-time setup (already done; kept for rebuilding the server)

1. `useradd --system --home-dir /opt/text2sql --shell /usr/sbin/nologin text2sql`. Then install `uv` to `/usr/local/bin`.
2. As `postgres`: `CREATE ROLE t2s_admin LOGIN CREATEROLE PASSWORD '…'`, then create `t2s_app` and `t2s_warehouse` owned by it. Also run `CREATE EXTENSION vector` in `t2s_app`, and `ALTER SCHEMA public OWNER TO t2s_admin` in `t2s_warehouse`. On Postgres 14 the admin role would otherwise lose `CREATE` once the grants file revokes it from `PUBLIC`.
3. Add these lines at the **top** of `pg_hba.conf`, so the read-only warehouse roles can reach nothing but their own database. Then reload.
   ```
   host  t2s_warehouse  wh_viewer,wh_analyst  127.0.0.1/32  scram-sha-256
   host  all            wh_viewer,wh_analyst  all           reject
   local all            wh_viewer,wh_analyst                reject
   ```
4. Write `/opt/text2sql/app/backend/.env` with random passwords and `JWT_SECRET` (`openssl rand -hex …`). Use the keys from `.env.example` and point `APP_DB_URL` and `WAREHOUSE_*` at `127.0.0.1`. Also set `REDIS_URL=redis://127.0.0.1:6379/5` and `ENV=prod`, and add the LLM API keys.
5. `uv sync --frozen --no-dev --python 3.12`, then run `python -m app.cli bootstrap` as `text2sql`.
6. Apply `app/warehouse/schema/04_hardening.sql` **as `postgres`** (pipe it via stdin). Revoking `set_config`/`pg_sleep` needs the superuser; bootstrap skips it with a warning otherwise.
7. Install the two unit files and enable them.
8. Install the HTTP half of the vhost and run `certbot certonly --webroot -w /var/www/text2sql.themeshub.net/public -d text2sql.themeshub.net`. Then add the HTTPS block and reload nginx, after `nginx -t` passes.

## Checks

```bash
curl https://text2sql.themeshub.net/api/health          # providers + circuit state
journalctl -u text2sql-api -f                            # structured JSON logs
```
