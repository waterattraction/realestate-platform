"""RepairJob 统一 CLI 入口."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Type

from scripts.ops.framework.base import RepairJob


def run_repair_cli(job_cls: Type[RepairJob]) -> int:
    job = job_cls()
    parser = argparse.ArgumentParser(
        description=f"Production data repair: {job.repair_name}",
    )
    parser.add_argument(
        "command",
        choices=["check", "dry-run", "apply", "verify", "rollback"],
    )
    parser.add_argument(
        "--out-dir",
        default=str(job.output_dir),
        help="dry-run output directory",
    )
    args = parser.parse_args()

    engine = job.create_engine()
    with engine.connect() as conn:
        ctx = job.make_context(conn, Path(args.out_dir))
        handlers = {
            "check": job.check,
            "dry-run": job.dry_run,
            "apply": job.apply,
            "verify": job.verify,
            "rollback": job.rollback,
        }
        try:
            return handlers[args.command](ctx)
        except Exception as exc:
            try:
                ctx.log("failed", remark=str(exc))
            except Exception:
                pass
            raise
