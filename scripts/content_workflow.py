#!/usr/bin/env python3
"""CLI for the bounded learning workflow."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path
from typing import Any

from learning_workflow.engine import (
    WorkflowError,
    apply_prepared_plan,
    build_context,
    dry_run_prepared_plan,
    prepare_transaction,
    register_source,
)

TOOLING_ROOT = Path(__file__).resolve().parents[1]

SYSTEM_OWNED_FIELDS = (
    "path",
    "revision",
    "created_at",
    "updated_at",
    "content_hash",
    "prepared_at",
    "plan_sha256",
    "payload_sha256",
    "provenance.transformation.run_id",
)


def read_json(path: Path | None) -> dict[str, Any]:
    source = "stdin" if path is None or str(path) == "-" else str(path)

    try:
        if path is None or str(path) == "-":
            text = sys.stdin.read()
        else:
            text = path.read_text(encoding="utf-8")

        value = json.loads(text)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise WorkflowError(
            f"cannot read JSON from {source}: {exc}"
        ) from exc

    if not isinstance(value, dict):
        raise WorkflowError(
            f"expected a JSON object from {source}"
        )

    return value


def emit(
    value: dict[str, Any],
    output: Path | None,
) -> None:
    text = json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
    ) + "\n"

    if output is None or str(output) == "-":
        sys.stdout.write(text)
        return

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    output.write_text(
        text,
        encoding="utf-8",
        newline="\n",
    )


def shell_command(parts: list[str]) -> str:
    return " \\\n  ".join(
        shlex.quote(part)
        for part in parts
    )


def render_chat_task(
    context: dict[str, Any],
    schema: dict[str, Any],
    content_workspace: Path,
    output: Path,
    prepared_plan_output: Path,
    dry_run_output: Path,
    apply_output: Path,
) -> str:
    del output

    context_json = json.dumps(
        context,
        ensure_ascii=False,
        indent=2,
    )
    schema_json = json.dumps(
        schema,
        ensure_ascii=False,
        indent=2,
    )

    cli = [
        "py",
        "-X",
        "utf8",
        "scripts/content_workflow.py",
        "--content-workspace",
        content_workspace.as_posix(),
    ]

    prepare = shell_command([
        *cli,
        "prepare",
    ])
    dry_run = shell_command([
        *cli,
        "apply",
        prepared_plan_output.as_posix(),
    ])
    execute = shell_command([
        *cli,
        "apply",
        prepared_plan_output.as_posix(),
        "--execute",
    ])

    prohibited = "\n".join(
        f"- `{field}`"
        for field in SYSTEM_OWNED_FIELDS
    )

    learning_goal_json = json.dumps(
        context["learning_goal"],
        ensure_ascii=False,
    )

    return f"""# Chat-ready bounded learning task

## Learning goal

{context["learning_goal"]}

## AI responsibility boundary

Return exactly one executable Git Bash command and no surrounding prose or code fences.
The JSON in its heredoc must validate against the transaction schema embedded below.
Use only the supplied bounded context.
Propose semantic learning content only.
Do not claim that anything was applied, committed, published, deployed, or learned.
Do not choose repository paths or assign these system-owned fields:

{prohibited}

For `update`, copy `expected_revision` and `expected_content_hash` from the matching context object.
For `create`, choose a semantic ID and an existing supported kind, but do not choose a repository path.
If the context does not support a safe update, propose a valid `create` or `unchanged` operation instead of inventing a target.

Return one complete pipe-friendly Git Bash command in this exact shape.
Replace the JSON body with the complete candidate transaction and do not add prose around the command:

```bash
mkdir -p .dx
{prepare} > {prepared_plan_output.as_posix()} <<'TRANSACTION'
{{
  "schema_version": "1.0",
  "learning_goal": {learning_goal_json},
  "operations": []
}}
TRANSACTION
```

## Authoritative transaction schema

```json
{schema_json}
```

## Deterministic bounded context

```json
{context_json}
```

## Prepare the immutable plan

The command above reads the candidate transaction once from UTF-8 stdin.
A successful prepared plan is the only stdout payload.
Shell redirection stores it as `{prepared_plan_output.as_posix()}`.
Diagnostics and failures use stderr.

## Dry-run the exact prepared plan

```bash
{dry_run} > {dry_run_output.as_posix()}
```

Review the transaction, prepared plan, and dry-run result.
Execution is a distinct human-reviewed command and must not be run automatically.

## Execute the same reviewed plan

```bash
{execute} > {apply_output.as_posix()}
```

After a short study interaction, record one unresolved point supplied by the learner.
Repository success must not be reported as learner mastery.
"""


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(
        description="Bounded AWS learning workflow"
    )
    top.add_argument(
        "--content-workspace",
        type=Path,
        required=True,
        help="backend worktree that owns content/**",
    )

    commands = top.add_subparsers(
        dest="command",
        required=True,
    )

    def add_query_arguments(
        command: argparse.ArgumentParser,
    ) -> None:
        command.add_argument(
            "--goal",
            required=True,
        )
        command.add_argument(
            "--id",
            action="append",
            default=[],
        )
        command.add_argument(
            "--alias",
            action="append",
            default=[],
        )
        command.add_argument(
            "--keyword",
            action="append",
            default=[],
        )
        command.add_argument(
            "--tag",
            action="append",
            default=[],
        )
        command.add_argument(
            "--kind",
            action="append",
            default=[],
        )
        command.add_argument(
            "--status",
            action="append",
            default=[],
        )
        command.add_argument(
            "--max-objects",
            type=int,
            default=20,
        )
        command.add_argument(
            "--no-related",
            action="store_true",
        )

    register = commands.add_parser("register-source", help="register a UTF-8 .txt or .md source")
    register.add_argument("source", type=Path)
    register.add_argument("--source-id", required=True)
    register.add_argument("--title", required=True)
    register.add_argument("--source-type", required=True, choices=("course_notes", "aws_docs", "book", "video", "own_notes"))
    register.add_argument("--language", default="en-US")
    register.add_argument("--execute", action="store_true")
    register.add_argument("-o", "--output", type=Path)

    query = commands.add_parser(
        "query",
        help="create a bounded learning context",
    )
    add_query_arguments(query)
    query.add_argument(
        "-o",
        "--output",
        type=Path,
    )

    task = commands.add_parser(
        "chat-task",
        help="create a non-mutating chat-ready task",
    )
    add_query_arguments(task)
    task.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path(".dx/iam-learning-task.md"),
    )
    task.add_argument(
        "--prepared-plan-output",
        type=Path,
        default=Path(".dx/iam-prepared-plan.json"),
    )
    task.add_argument(
        "--dry-run-output",
        type=Path,
        default=Path(".dx/iam-dry-run-result.json"),
    )
    task.add_argument(
        "--apply-output",
        type=Path,
        default=Path(".dx/iam-apply-result.json"),
    )

    prepare = commands.add_parser(
        "prepare",
        help=(
            "turn a candidate transaction into an "
            "immutable prepared plan"
        ),
    )
    prepare.add_argument(
        "transaction",
        type=Path,
        nargs="?",
        help=(
            "JSON file; omit or use - to read "
            "UTF-8 JSON from stdin"
        ),
    )
    prepare.add_argument(
        "-o",
        "--output",
        type=Path,
        help=(
            "JSON file; omit or use - to write "
            "JSON to stdout"
        ),
    )

    apply = commands.add_parser(
        "apply",
        help=(
            "validate a prepared plan; "
            "write only with --execute"
        ),
    )
    apply.add_argument(
        "prepared_plan",
        type=Path,
    )
    apply.add_argument(
        "--execute",
        action="store_true",
    )
    apply.add_argument(
        "-o",
        "--output",
        type=Path,
    )

    return top


def query_request(
    args: argparse.Namespace,
) -> dict[str, Any]:
    return {
        "learning_goal": args.goal,
        "ids": args.id,
        "aliases": args.alias,
        "keywords": args.keyword,
        "tags": args.tag,
        "kinds": args.kind,
        "statuses": args.status,
        "max_objects": args.max_objects,
        "include_direct_relationships": not args.no_related,
    }


def main() -> int:
    args = parser().parse_args()

    content_workspace = (
        args.content_workspace
        .expanduser()
        .resolve()
    )

    try:
        if args.command == "register-source":
            result = register_source(
                content_workspace, args.source.expanduser().resolve(), args.source_id,
                args.title, args.source_type, args.language, args.execute,
            )
        elif args.command in {
            "query",
            "chat-task",
        }:
            result = build_context(
                content_workspace,
                query_request(args),
            )

            if args.command == "chat-task":
                schema = read_json(
                    TOOLING_ROOT
                    / "schemas"
                    / "learning-transaction.schema.json"
                )

                text = render_chat_task(
                    result,
                    schema,
                    content_workspace,
                    args.output,
                    args.prepared_plan_output,
                    args.dry_run_output,
                    args.apply_output,
                )

                args.output.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )
                args.output.write_text(
                    text,
                    encoding="utf-8",
                    newline="\n",
                )

                print(
                    f"INFO chat task: "
                    f"{args.output.as_posix()}",
                    file=sys.stderr,
                )
                print(
                    f"INFO expected prepared plan: "
                    f"{args.prepared_plan_output.as_posix()}",
                    file=sys.stderr,
                )
                return 0

        elif args.command == "prepare":
            result = prepare_transaction(
                TOOLING_ROOT,
                content_workspace,
                read_json(args.transaction),
            )

        elif args.execute:
            result = apply_prepared_plan(
                TOOLING_ROOT,
                content_workspace,
                read_json(args.prepared_plan),
            )

        else:
            result = dry_run_prepared_plan(
                TOOLING_ROOT,
                content_workspace,
                read_json(args.prepared_plan),
            )

        emit(
            result,
            getattr(args, "output", None),
        )
        return 0

    except WorkflowError as exc:
        failure = {
            "schema_version": "1.0",
            "operation": args.command,
            "result": "failure",
            "failure": {
                "category": "workflow_error",
                "phase": args.command,
                "reason": str(exc),
            },
            "next_actions": [
                "correct the input or create a fresh bounded context"
            ],
        }

        sys.stderr.write(
            json.dumps(
                failure,
                ensure_ascii=False,
                indent=2,
            ) + "\n"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
