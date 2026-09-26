import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.demo_users import seed_demo_users
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.migrate import upgrade_head
from app.eval.seed import seed_eval_cases
from app.warehouse.bootstrap import bootstrap_warehouse

BASELINE = Path(__file__).resolve().parents[1] / "eval" / "baseline.json"


async def _seed_app_data(settings: Settings) -> tuple[int, int]:
    engine = create_async_engine(settings.app_db_url)
    try:
        async with async_sessionmaker(engine)() as session:
            users = await seed_demo_users(session, settings.demo_password.get_secret_value())
            cases = await seed_eval_cases(session)
            return users, cases
    finally:
        await engine.dispose()


def bootstrap(settings: Settings) -> None:
    """Migrate app-db, prepare + seed warehouse, create demo users and eval cases. Idempotent."""
    log = structlog.get_logger()
    upgrade_head(settings.app_db_url)
    log.info("app_db.migrated")
    counts = bootstrap_warehouse(settings, scale=settings.warehouse_seed_scale)
    log.info("warehouse.ready", **counts)
    created, cases = asyncio.run(_seed_app_data(settings))
    log.info("demo_users.ready", created=created)
    log.info("eval_cases.ready", cases=cases)


async def _eval(settings: Settings, args: argparse.Namespace) -> dict[str, Any]:
    from app.eval.runner import create_run, execute_run, validate_mode
    from app.services.container import build_services, connect_redis

    engine = create_async_engine(settings.app_db_url)
    redis = await connect_redis(settings.redis_url)
    try:
        services = build_services(
            settings, async_sessionmaker(engine, expire_on_commit=False), redis=redis
        )
        if args.cassette == "replay":
            services.providers = {}  # replay providers come from the cassette itself
        validate_mode(
            args.mode, sorted(services.providers) or ["anthropic", "openai", "gemini", "ollama"]
        )
        async with services.sessionmaker() as session:
            await seed_eval_cases(session)
        run = await create_run(services, args.suite, args.mode, None)
        summary: dict[str, Any] = await execute_run(services, run.id, cassette_mode=args.cassette,
                                                    concurrency=args.concurrency)  # fmt: skip
    finally:
        if redis:
            await redis.aclose()
        await engine.dispose()
    return {"run_id": str(run.id), "suite": args.suite, "mode": args.mode, **summary}


def report_and_gate(report: dict[str, Any], args: argparse.Namespace) -> int:
    print(
        json.dumps(
            {k: v for k, v in report.items() if not k.startswith("by_")},
            indent=2,
            ensure_ascii=False,
        )
    )
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False))
    if args.update_baseline:
        keep = ("suite", "mode", "ex", "behavior_accuracy", "guardrail_recall", "cases")
        BASELINE.write_text(json.dumps({k: report[k] for k in keep}, indent=2) + "\n")
        print(f"baseline written to {BASELINE}")
    if args.gate:
        from app.eval.runner import gate

        problems = gate(report, json.loads(Path(args.gate).read_text()))
        for problem in problems:
            print(f"GATE FAILED: {problem}", file=sys.stderr)
        return 1 if problems else 0
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("bootstrap", help="migrate, seed warehouse, demo users and eval cases")
    commands.add_parser("seed-eval", help="load eval/datasets/*.yaml into eval_cases")
    run_eval = commands.add_parser("eval", help="run the eval harness")
    run_eval.add_argument("--suite", default="smoke", help="smoke | full | review")
    run_eval.add_argument("--mode", default="chain", help="chain | rule_based | provider=<name>")
    run_eval.add_argument("--cassette", default="off", choices=["off", "record", "replay"])
    run_eval.add_argument("--concurrency", type=int, default=4)
    run_eval.add_argument("--out", help="write the full JSON report here")
    run_eval.add_argument(
        "--gate", help="baseline JSON; exit 1 if EX drops >2 points or an attack leaks"
    )
    run_eval.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args(argv)
    settings = get_settings()
    configure_logging(settings.env)
    if args.command == "bootstrap":
        bootstrap(settings)
    elif args.command == "seed-eval":
        print(asyncio.run(_seed_app_data(settings))[1], "eval cases")
    elif args.command == "eval":
        sys.exit(report_and_gate(asyncio.run(_eval(settings, args)), args))


if __name__ == "__main__":
    main()
