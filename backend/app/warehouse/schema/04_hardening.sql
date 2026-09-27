-- Needs a superuser (these functions belong to pg_catalog). bootstrap runs it when it can and
-- warns otherwise; deploy/deploy.sh applies it as postgres on the shared production server.
REVOKE EXECUTE ON FUNCTION pg_catalog.set_config(text, text, boolean) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION pg_catalog.pg_sleep(double precision) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION pg_catalog.pg_sleep_for(interval) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION pg_catalog.pg_sleep_until(timestamp with time zone) FROM PUBLIC;
