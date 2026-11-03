#!/usr/bin/env python3
"""CLI for the bounded learning workflow."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from learning_workflow.engine import (
    WorkflowError,
    apply_prepared_plan,
    build_context,
    dry_run_prepared_plan,
    prepare_transaction,
)

TOOLING_ROOT = Path(__file__).resolve().parents[1]


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise WorkflowError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise WorkflowError(f"expected a JSON object: {path}")
    return value


def emit(value: dict[str, Any], output: Path | None) -> None:
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if output is None or str(output) == "-":
        sys.stdout.write(text)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8", newline="\n")


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(description="Bounded AWS learning workflow")
    top.add_argument(
        "--content-workspace",
        type=Path,
        required=True,
        help="backend worktree that owns content/**",
    )
    commands = top.add_subparsers(dest="command", required=True)

    query = commands.add_parser("query", help="create a bounded learning context")
    query.add_argument("--goal", required=True)
    query.add_argument("--id", action="append", default=[])
    query.add_argument("--alias", action="append", default=[])
    query.add_argument("--keyword", action="append", default=[])
    query.add_argument("--tag", action="append", default=[])
    query.add_argument("--kind", action="append", default=[])
    query.add_argument("--status", action="append", default=[])
    query.add_argument("--max-objects", type=int, default=20)
    query.add_argument("--no-related", action="store_true")
    query.add_argument("-o", "--output", type=Path)

    prepare = commands.add_parser(
        "prepare", help="turn a candidate transaction into an immutable prepared plan"
    )
    prepare.add_argument("transaction", type=Path)
    prepare.add_argument("-o", "--output", type=Path, required=True)

    apply = commands.add_parser(
        "apply", help="validate a prepared plan; write only with --execute"
    )
    apply.add_argument("prepared_plan", type=Path)
    apply.add_argument("--execute", action="store_true")
    apply.add_argument("-o", "--output", type=Path)
    return top


def main() -> int:
    args = parser().parse_args()
    content_workspace = args.content_workspace.expanduser().resolve()
    try:
        if args.command == "query":
            result = build_context(
                content_workspace,
                {
                    "learning_goal": args.goal,
                    "ids": args.id,
                    "aliases": args.alias,
                    "keywords": args.keyword,
                    "tags": args.tag,
                    "kinds": args.kind,
                    "statuses": args.status,
                    "max_objects": args.max_objects,
                    "include_direct_relationships": not args.no_related,
                },
            )
        elif args.command == "prepare":
            result = prepare_transaction(
                TOOLING_ROOT, content_workspace, read_json(args.transaction)
            )
        elif args.execute:
            result = apply_prepared_plan(
                TOOLING_ROOT, content_workspace, read_json(args.prepared_plan)
            )
        else:
            result = dry_run_prepared_plan(
                TOOLING_ROOT, content_workspace, read_json(args.prepared_plan)
            )
        emit(result, getattr(args, "output", None))
        return 0
    except WorkflowError as exc:
        emit(
            {
                "schema_version": "1.0",
                "operation": args.command,
                "result": "failure",
                "failure": {"category": "workflow_error", "reason": str(exc)},
                "next_actions": ["correct the input or create a fresh bounded context"],
            },
            getattr(args, "output", None),
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
