"""Operator commands. Run from apps/api:  python -m app.cli <command> --help

seed                 load taxonomy, roles, learning content and built-in sources
ingest-adzuna        fetch postings from Adzuna now (needs ADZUNA_APP_ID / ADZUNA_APP_KEY)
import-file          import a licensed CSV/JSON/JSONL dataset of postings
extract              extract skills from pending postings, then refresh demand
reextract            re-extract postings processed by an older taxonomy/extractor version
refresh-demand       rebuild the monthly skill demand series
reclassify-roles     re-assign posting roles with the current roles.json, then refresh demand
parse-curriculum     upload and parse a syllabus PDF for a program, synchronously
regrade-curriculum   recompute unit skill coverage with the current taxonomy
export-eval-sample   write a random sample of stored postings for hand labelling
eval-extraction      precision / recall / F1 on a labelled set (optionally calibrate)
import-esco          link curated skills to ESCO concepts from the ESCO skills CSV
create-user          create an account (e.g. the first admin); password from a prompt or stdin
"""

import argparse
import getpass
import json
import random
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.workers.db import run_with_db

Factory = async_sessionmaker[AsyncSession]


def _print(data: Any) -> None:
    print(json.dumps(data, indent=2, default=str))


async def cmd_seed(factory: Factory, _: argparse.Namespace) -> None:
    from app.seed.loader import seed_reference_data

    async with factory() as session:
        result = await seed_reference_data(session)
        await session.commit()
    _print(result.__dict__)


async def _post_ingest(factory: Factory) -> dict[str, int]:
    from app.services.analytics.demand import refresh_monthly_demand
    from app.services.extraction.service import extract_pending

    extracted = await extract_pending(factory)
    async with factory() as session:
        rows = await refresh_monthly_demand(session)
        await session.commit()
    return {"extracted": extracted, "demand_rows": rows}


async def cmd_ingest_adzuna(factory: Factory, args: argparse.Namespace) -> None:
    from app.models import JobSource
    from app.services.ingestion.adzuna import AdzunaConnector
    from app.services.ingestion.runner import create_run, execute_run

    settings = get_settings()
    connector = AdzunaConnector(settings)
    params = {
        k: v
        for k, v in vars(args).items()
        if k in ("country", "what", "where", "category", "pages", "max_days_old") and v
    }
    params = AdzunaConnector.validate_params(params, settings.ADZUNA_MAX_PAGES_PER_RUN)
    async with factory() as session:
        source = await session.scalar(select(JobSource).where(JobSource.key == "adzuna"))
        if source is None:
            sys.exit("Source 'adzuna' missing: run `python -m app.cli seed` first")
        run = await create_run(session, source, params)
        await session.commit()
        run_id = run.id
    counts = await execute_run(factory, run_id, connector)
    _print(
        {
            "run_id": run_id,
            "fetched": counts.fetched,
            "inserted": counts.inserted,
            "duplicates": counts.duplicates,
            "errors": counts.errors,
            "error_samples": counts.error_samples,
            **await _post_ingest(factory),
        }
    )


async def cmd_import_file(factory: Factory, args: argparse.Namespace) -> None:
    from app.services.ingestion.file_import import FileConnector
    from app.services.ingestion.runner import create_run, execute_run, get_or_create_source

    mapping = dict(pair.split("=", 1) for pair in args.map) if args.map else {}
    connector = FileConnector(Path(args.path), mapping)
    async with factory() as session:
        source = await get_or_create_source(
            session,
            args.source,
            name=args.name,
            kind="file",
            is_synthetic=args.synthetic,
            licence=args.licence,
        )
        if not source.licence and not source.is_synthetic:
            sys.exit("A new real data source needs --licence (who published it, under what terms)")
        run = await create_run(session, source, {"file": Path(args.path).name, "map": mapping})
        await session.commit()
        run_id = run.id
    counts = await execute_run(factory, run_id, connector)
    _print(
        {
            "run_id": run_id,
            "fetched": counts.fetched,
            "inserted": counts.inserted,
            "duplicates": counts.duplicates,
            "errors": counts.errors,
            "error_samples": counts.error_samples,
            **await _post_ingest(factory),
        }
    )


async def cmd_extract(factory: Factory, _: argparse.Namespace) -> None:
    _print(await _post_ingest(factory))


async def cmd_reextract(factory: Factory, _: argparse.Namespace) -> None:
    from app.services.extraction.service import mark_stale

    async with factory() as session:
        marked = await mark_stale(session)
        await session.commit()
    _print({"marked": marked, **await _post_ingest(factory)})


async def cmd_reclassify_roles(factory: Factory, _: argparse.Namespace) -> None:
    from app.services.analytics.demand import refresh_monthly_demand
    from app.services.roles import reclassify_postings

    async with factory() as session:
        result = await reclassify_postings(session)
        result["demand_rows"] = await refresh_monthly_demand(session)
        await session.commit()
    _print(result)


async def cmd_refresh_demand(factory: Factory, _: argparse.Namespace) -> None:
    from app.services.analytics.demand import refresh_monthly_demand

    async with factory() as session:
        rows = await refresh_monthly_demand(session)
        await session.commit()
    _print({"demand_rows": rows})


async def cmd_parse_curriculum(factory: Factory, args: argparse.Namespace) -> None:
    from app.services.curriculum.service import create_document, parse_document

    settings = get_settings()
    path = Path(args.path)
    async with factory() as session:
        doc, created = await create_document(
            session, args.program_id, path.name, path.read_bytes(), settings
        )
        await session.commit()
        doc_id = doc.id
    parsed = await parse_document(factory, doc_id, settings)
    _print(
        {
            "document_id": doc_id,
            "created": created,
            "status": parsed.status,
            "strategy": parsed.parser_strategy,
            "units": parsed.units_parsed,
            "error": parsed.error,
        }
    )


async def cmd_regrade(factory: Factory, _: argparse.Namespace) -> None:
    from app.services.curriculum.service import recompute_unit_skills

    async with factory() as session:
        units = await recompute_unit_skills(session)
        await session.commit()
    _print({"units_regraded": units})


async def cmd_export_sample(factory: Factory, args: argparse.Namespace) -> None:
    from app.models import JobPosting, JobSource

    async with factory() as session:
        rows = (
            await session.execute(
                select(
                    JobPosting.id,
                    JobSource.key,
                    JobPosting.external_id,
                    JobPosting.title,
                    JobPosting.description,
                )
                .join(JobSource, JobSource.id == JobPosting.source_id)
                .where(JobSource.is_synthetic.is_(False))
                .order_by(func.md5(func.concat(JobPosting.id, str(args.seed))))
                .limit(args.n)
            )
        ).all()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for _id, source, ext, title, desc in rows:
            fh.write(
                json.dumps(
                    {
                        "id": f"{source}:{ext}",
                        "title": title,
                        "description": desc,
                        "skills": [],
                        "labelled_by": None,
                        "labelled_at": None,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    _print(
        {
            "written": len(rows),
            "path": str(out),
            "next": "fill in 'skills' (taxonomy slugs) and 'labelled_by' for every line",
        }
    )


def cmd_eval(args: argparse.Namespace) -> None:
    from app.services.extraction.evaluation import calibrate, evaluate, load_eval_set
    from app.services.extraction.extractor import SkillExtractor, load_calibration
    from app.services.extraction.taxonomy import specs_from_seed

    specs = specs_from_seed()
    extractor = SkillExtractor(specs)
    items = load_eval_set(Path(args.path), {s.slug for s in specs})
    unlabelled = [i.id for i in items if not i.skills]
    report = evaluate(extractor, items)
    result: dict[str, Any] = {
        "eval_set": Path(args.path).name,
        "extractor": extractor.version,
        **report.as_dict(),
    }
    if unlabelled:
        result["warning"] = f"{len(unlabelled)} postings have no labelled skills"
    if args.errors:
        result["errors"] = report.errors
    if args.calibrate:
        cal_path = Path(__file__).parent / "services" / "extraction" / "calibration.json"
        new = calibrate(report, load_calibration(), Path(args.path).name)
        cal_path.write_text(json.dumps(new, indent=2) + "\n", encoding="utf-8")
        result["calibration"] = new
    if args.report:
        Path(args.report).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    _print(result)
    if report.f1 < args.min_f1:
        sys.exit(f"Extraction F1 {report.f1:.4f} is below the gate of {args.min_f1}")


async def cmd_import_esco(factory: Factory, args: argparse.Namespace) -> None:
    from app.seed.esco import import_esco

    async with factory() as session:
        result = await import_esco(session, Path(args.path), include_unlinked=args.include_unlinked)
        await session.commit()
    _print(result.__dict__)


def _read_password(args: argparse.Namespace) -> str:
    """From stdin (--password-stdin) or an interactive prompt; never a command-line argument,
    which would end up in shell history and process listings."""
    if args.password_stdin:
        return sys.stdin.readline().rstrip("\r\n")
    first = getpass.getpass("Password: ")
    if getpass.getpass("Repeat password: ") != first:
        sys.exit("Passwords do not match")
    return first


async def cmd_create_user(factory: Factory, args: argparse.Namespace) -> None:
    from app.services import audit
    from app.services.auth.service import create_user

    password = _read_password(args)
    async with factory() as session:
        user = await create_user(session, args.email, password, role=args.role)
        audit.record(
            session,
            "user.create",
            actor_role="cli",
            target_type="user",
            target_id=user.id,
            details={"role": user.role, "via": "cli"},
        )
        await session.commit()
    _print({"id": str(user.id), "email": user.email, "role": user.role})


ASYNC_COMMANDS: dict[str, Callable[[Factory, argparse.Namespace], Awaitable[None]]] = {
    "seed": cmd_seed,
    "ingest-adzuna": cmd_ingest_adzuna,
    "import-file": cmd_import_file,
    "extract": cmd_extract,
    "reextract": cmd_reextract,
    "refresh-demand": cmd_refresh_demand,
    "reclassify-roles": cmd_reclassify_roles,
    "parse-curriculum": cmd_parse_curriculum,
    "regrade-curriculum": cmd_regrade,
    "export-eval-sample": cmd_export_sample,
    "import-esco": cmd_import_esco,
    "create-user": cmd_create_user,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name in (
        "seed",
        "extract",
        "reextract",
        "refresh-demand",
        "reclassify-roles",
        "regrade-curriculum",
    ):
        sub.add_parser(name)

    p = sub.add_parser("ingest-adzuna")
    p.add_argument("--country", default="in")
    p.add_argument("--what")
    p.add_argument("--where")
    p.add_argument("--category")
    p.add_argument("--pages", type=int, default=1)
    p.add_argument("--max-days-old", type=int)

    p = sub.add_parser("import-file")
    p.add_argument("--path", required=True)
    p.add_argument("--source", required=True, help="source key, e.g. kaggle-xyz-2024")
    p.add_argument("--name", help="display name for a new source")
    p.add_argument("--licence", help="required for a new non-synthetic source")
    p.add_argument(
        "--synthetic",
        action="store_true",
        help="mark the source synthetic (excluded from analytics)",
    )
    p.add_argument(
        "--map",
        nargs="*",
        metavar="FIELD=COLUMN",
        help="column map, e.g. title=job_title posted_at=date",
    )

    p = sub.add_parser("parse-curriculum")
    p.add_argument("--program-id", type=int, required=True)
    p.add_argument("--path", required=True)

    p = sub.add_parser("export-eval-sample")
    p.add_argument("--n", type=int, default=120)
    p.add_argument("--seed", type=int, default=random.randrange(1_000_000))
    p.add_argument("--out", required=True)

    p = sub.add_parser("create-user")
    p.add_argument("--email", required=True)
    p.add_argument("--role", choices=["student", "faculty", "admin"], default="admin")
    p.add_argument("--password-stdin", action="store_true", help="read the password from stdin")

    p = sub.add_parser("eval-extraction")
    p.add_argument("--path", required=True)
    p.add_argument("--calibrate", action="store_true")
    p.add_argument("--errors", action="store_true", help="list false positives/negatives")
    p.add_argument("--report", help="also write the result JSON here")
    p.add_argument("--min-f1", type=float, default=0.0, help="fail if F1 is below this")

    p = sub.add_parser("import-esco")
    p.add_argument("--path", required=True)
    p.add_argument("--include-unlinked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    configure_logging(get_settings().LOG_LEVEL, json_output=False)
    if args.command == "eval-extraction":
        cmd_eval(args)
        return
    command = ASYNC_COMMANDS[args.command]
    run_with_db(lambda factory: command(factory, args))


if __name__ == "__main__":
    main()
