#!/usr/bin/env python3
"""Bounded chat-AI authoring transaction CLI."""

from __future__ import annotations

import argparse
import copy
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from authoring_common import (
    AuthoringError,
    KIND_PATHS,
    ROOT,
    SYSTEM_FIELDS,
    content_hash,
    derive_path,
    load_objects,
    normalize_text,
    packet_hash,
    read_yaml,
    sha256,
    split_fragments,
    validate_object,
    write_yaml,
)


SOURCE_TYPES = {
    "course_notes",
    "aws_docs",
    "book",
    "video",
    "own_notes",
}

SOURCE_METADATA_POLICIES = {
    "forbidden",
    "allowed",
}

ALLOWED_ACTIONS = {
    "create",
    "update",
}


def now_utc() -> str:
    """Return an authoritative UTC timestamp."""

    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def require_backend(path: Path) -> Path:
    """Resolve and validate the explicit backend workspace."""

    backend = path.expanduser().resolve()
    content = backend / "content"

    if not content.is_dir():
        raise AuthoringError(
            f"backend content directory is missing: {content}"
        )

    return backend


def command_ingest(args: argparse.Namespace) -> None:
    """Create a deterministic packet from UTF-8 text."""

    source = args.input.expanduser().resolve()

    if source.suffix.lower() not in {".txt", ".md"}:
        raise AuthoringError(
            "increment 1 accepts only UTF-8 .txt and .md sources"
        )

    try:
        raw = source.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise AuthoringError(
            f"cannot read UTF-8 source {source}: {error}"
        ) from error

    if not normalize_text(text):
        raise AuthoringError("source is empty")

    fragments: list[dict[str, Any]] = []

    for index, (start, end, exact) in enumerate(
        split_fragments(text),
        1,
    ):
        normalized = normalize_text(exact)

        fragments.append(
            {
                "id": (
                    f"{args.source_id}.fragment.{index:03d}"
                ),
                "language": args.language,
                "content_fingerprint": sha256(normalized)[:32],
                "locator": {
                    "start_offset": start,
                    "end_offset": end,
                },
                "exact_text": exact,
                "normalized_text": normalized,
                "noise_removed": [],
            }
        )

    packet: dict[str, Any] = {
        "packet_version": "1.0",
        "source": {
            "id": args.source_id,
            "source_type": args.source_type,
            "title": args.title,
            "language": args.language,
            "origin": {
                "path": args.input.as_posix(),
                "external_url": args.external_url,
                "content_hash": sha256(raw),
            },
        },
        "fragments": fragments,
        "publication_policy": {
            "source_metadata": args.source_metadata,
            "exact_text": "forbidden",
            "derived_content": "candidate_only",
        },
    }

    packet["packet_hash"] = packet_hash(packet)
    write_yaml(args.output, packet)

    print(f"[authoring] packet: {args.output}")
    print(f"[authoring] fragments: {len(fragments)}")
    print(
        f"[authoring] source metadata policy: "
        f"{args.source_metadata}"
    )
    print(
        f"[authoring] packet hash: "
        f"{packet['packet_hash']}"
    )


def schema_contracts(kinds: list[str]) -> str:
    """Return the selected existing schemas for task generation."""

    blocks: list[str] = []
    common_path = ROOT / "schemas" / "common.schema.json"

    if not common_path.is_file():
        raise AuthoringError(
            f"common schema is missing: {common_path}"
        )

    common = common_path.read_text(encoding="utf-8")

    blocks.append(
        "### common\n"
        "```json\n"
        f"{common}\n"
        "```"
    )

    for kind in kinds:
        path = (
            ROOT
            / "schemas"
            / f"{kind.replace('_', '-')}.schema.json"
        )

        if not path.is_file():
            raise AuthoringError(
                f"unsupported kind for prepare: {kind}"
            )

        blocks.append(
            f"### {kind}\n"
            "```json\n"
            f"{path.read_text(encoding='utf-8')}\n"
            "```"
        )

    return "\n\n".join(blocks)


def command_prepare(args: argparse.Namespace) -> None:
    """Generate the bounded task to give to the chat AI."""

    backend = require_backend(args.backend)
    packet = read_yaml(args.packet)

    if packet_hash(packet) != packet.get("packet_hash"):
        raise AuthoringError(
            "packet hash does not match packet contents"
        )

    kinds = [
        value.strip()
        for value in args.kinds.split(",")
        if value.strip()
    ]

    if not kinds:
        raise AuthoringError(
            "--kinds must contain at least one kind"
        )

    objects = load_objects(backend)
    source_id = packet.get("source", {}).get("id")

    if (
        source_id not in objects
        or objects[source_id][1].get("kind") != "source"
    ):
        raise AuthoringError(
            f"{source_id} is not registered in backend content"
        )

    existing = [
        document
        for _, document in objects.values()
        if document.get("kind") in kinds
    ]

    response = (
        Path(".authoring")
        / "responses"
        / f"{args.packet.stem}.yaml"
    )

    packet_yaml = yaml.safe_dump(
        packet,
        sort_keys=False,
        allow_unicode=True,
    )

    existing_yaml = yaml.safe_dump(
        existing,
        sort_keys=False,
        allow_unicode=True,
    )

    task = f"""# Bounded authoring task

Return exactly one YAML mapping and no surrounding prose or code fences.

## Non-negotiable rules

1. Return `transaction_version: "1.0"`, a stable `transaction_id`,
   the exact `source_packet_hash`, `operations`, and `unresolved`.
2. Use only `create` and `update`.
3. Do not choose repository paths.
4. Every object must have `status: candidate`.
5. Every substantive claim must cite registered source and fragment IDs.
6. Do not include `revision`, `created_at`, `updated_at`, or `content_hash`.
7. Do not include `provenance.transformation.run_id`.
8. For updates, provide `id` and `expected_content_hash` from existing context.
9. Do not reproduce restricted, private, or licensed source passages.
10. Paraphrase source material into original learning content.
11. Put uncertain claims in `grounding.unsupported_claims`.
12. Put transaction-level uncertainties in `unresolved`.
13. Use an `llm_*` provenance transformation method.
14. Preserve existing semantic IDs instead of creating near-duplicates.
15. Do not claim application, validation, commit, or publication.

## Transaction shape

```yaml
transaction_version: "1.0"
transaction_id: authoring.example.001
source_packet_hash: {packet["packet_hash"]}
operations:
  - action: create
    kind: concept
    object:
      # Complete candidate object without Python-owned system fields.
  - action: update
    kind: concept
    id: concept.example
    expected_content_hash: <current 64-character hash>
    object:
      # Complete candidate replacement without Python-owned system fields.
unresolved: []
```

## Source packet

```yaml
{packet_yaml}```

## Existing objects for collision checking and updates

```yaml
{existing_yaml}```

## Repository schema contracts

{schema_contracts(kinds)}
"""

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    args.output.write_text(
        task,
        encoding="utf-8",
        newline="\n",
    )

    print(f"[authoring] task: {args.output}")
    print(f"Save the AI response to: {response.as_posix()}")
    print("Then run:")
    print(
        "py scripts/authoring.py apply "
        f"--transaction {response.as_posix()} "
        f"--packet {args.packet} "
        f"--backend {args.backend} "
        "--dry-run"
    )
    print(
        "py scripts/authoring.py apply "
        f"--transaction {response.as_posix()} "
        f"--packet {args.packet} "
        f"--backend {args.backend}"
    )


def validate_envelope(transaction: dict[str, Any]) -> None:
    """Validate the portable transaction envelope."""

    allowed = {
        "transaction_version",
        "transaction_id",
        "source_packet_hash",
        "operations",
        "unresolved",
    }

    extra = set(transaction) - allowed

    if extra:
        raise AuthoringError(
            "unknown transaction fields: "
            + ", ".join(sorted(extra))
        )

    if transaction.get("transaction_version") != "1.0":
        raise AuthoringError(
            "transaction_version must be 1.0"
        )

    transaction_id = transaction.get("transaction_id")

    if (
        not isinstance(transaction_id, str)
        or not transaction_id.strip()
    ):
        raise AuthoringError(
            "transaction_id is required"
        )

    if not re.fullmatch(
        r"sha256:[a-f0-9]{64}",
        str(transaction.get("source_packet_hash", "")),
    ):
        raise AuthoringError(
            "source_packet_hash must be "
            "sha256:<64 lowercase hex characters>"
        )

    operations = transaction.get("operations")

    if not isinstance(operations, list) or not operations:
        raise AuthoringError(
            "operations must be a non-empty list"
        )

    if not isinstance(transaction.get("unresolved", []), list):
        raise AuthoringError(
            "unresolved must be a list"
        )


def require_registered_source(
    packet: dict[str, Any],
    objects: dict[str, tuple[Path, dict[str, Any]]],
) -> dict[str, set[str]]:
    """Require exact packet-to-backend source correspondence."""

    packet_source = packet.get("source")

    if not isinstance(packet_source, dict):
        raise AuthoringError(
            "packet source must be a mapping"
        )

    source_id = packet_source.get("id")

    if (
        source_id not in objects
        or objects[source_id][1].get("kind") != "source"
    ):
        raise AuthoringError(
            f"{source_id} is not registered in backend content"
        )

    registered = objects[source_id][1]

    packet_origin = packet_source.get("origin", {})
    registered_origin = registered.get("origin", {})

    packet_content_hash = packet_origin.get("content_hash")
    registered_content_hash = registered_origin.get(
        "content_hash"
    )

    if packet_content_hash != registered_content_hash:
        raise AuthoringError(
            "registered source content hash does not "
            f"match packet: {source_id}"
        )

    packet_fragments = packet.get("fragments")

    if not isinstance(packet_fragments, list):
        raise AuthoringError(
            "packet fragments must be a list"
        )

    registered_fragments = registered.get("fragments")

    if not isinstance(registered_fragments, list):
        raise AuthoringError(
            f"registered source has no fragments: {source_id}"
        )

    packet_index = {
        fragment.get("id"): fragment.get(
            "content_fingerprint"
        )
        for fragment in packet_fragments
        if isinstance(fragment, dict)
    }

    registered_index = {
        fragment.get("id"): fragment.get(
            "content_fingerprint"
        )
        for fragment in registered_fragments
        if isinstance(fragment, dict)
    }

    if packet_index != registered_index:
        raise AuthoringError(
            "registered source fragments do not "
            f"match packet: {source_id}"
        )

    if not packet_index:
        raise AuthoringError(
            f"packet contains no source fragments: {source_id}"
        )

    return {
        source_id: set(packet_index),
    }


def verify_evidence(
    document: dict[str, Any],
    sources: dict[str, set[str]],
) -> None:
    """Verify provenance and grounding against registered fragments."""

    provenance = document.get("provenance")
    grounding = document.get("grounding")

    if not isinstance(provenance, dict):
        raise AuthoringError(
            f"{document.get('id')} must include provenance"
        )

    if not isinstance(grounding, dict):
        raise AuthoringError(
            f"{document.get('id')} must include grounding"
        )

    references = provenance.get("sources")

    if not isinstance(references, list) or not references:
        raise AuthoringError(
            f"{document.get('id')} has no provenance sources"
        )

    pairs: set[tuple[str, str]] = set()

    for reference in references:
        if not isinstance(reference, dict):
            raise AuthoringError(
                f"invalid provenance source in "
                f"{document.get('id')}"
            )

        source_id = reference.get("source_id")
        fragment_id = reference.get("fragment_id")

        if (
            source_id not in sources
            or fragment_id not in sources[source_id]
        ):
            raise AuthoringError(
                "unknown source fragment "
                f"{source_id}/{fragment_id} "
                f"in {document.get('id')}"
            )

        pairs.add((source_id, fragment_id))

    expected_source_ids = {
        source_id
        for source_id, _ in pairs
    }

    expected_fragment_ids = {
        fragment_id
        for _, fragment_id in pairs
    }

    if set(grounding.get("source_ids", [])) != expected_source_ids:
        raise AuthoringError(
            "grounding.source_ids disagrees with "
            f"provenance in {document.get('id')}"
        )

    if (
        set(grounding.get("fragment_ids", []))
        != expected_fragment_ids
    ):
        raise AuthoringError(
            "grounding.fragment_ids disagrees with "
            f"provenance in {document.get('id')}"
        )


def enrich_operation(
    operation: dict[str, Any],
    existing: dict[str, tuple[Path, dict[str, Any]]],
    sources: dict[str, set[str]],
    run_id: str,
    timestamp: str,
    backend: Path,
) -> tuple[str, Path, dict[str, Any]]:
    """Validate and complete one semantic operation."""

    action = operation.get("action")
    kind = operation.get("kind")
    proposed = operation.get("object")

    if action not in ALLOWED_ACTIONS:
        raise AuthoringError(
            f"unsupported operation action: {action}"
        )

    if (
        kind not in KIND_PATHS
        or kind in {"source", "generation_run"}
    ):
        raise AuthoringError(
            f"unsupported authoring kind: {kind}"
        )

    if not isinstance(proposed, dict):
        raise AuthoringError(
            "operation.object must be a mapping"
        )

    supplied = SYSTEM_FIELDS & set(proposed)

    if supplied:
        raise AuthoringError(
            "AI supplied authoritative fields for "
            f"{proposed.get('id')}: "
            + ", ".join(sorted(supplied))
        )

    document = copy.deepcopy(proposed)
    object_id = document.get("id")

    if document.get("kind") != kind:
        raise AuthoringError(
            f"kind mismatch for {object_id}"
        )

    if document.get("status") != "candidate":
        raise AuthoringError(
            f"AI-authored object must be candidate: {object_id}"
        )

    if (
        action == "update"
        and operation.get("id") != object_id
    ):
        raise AuthoringError(
            "update operation id must equal object.id"
        )

    provenance = document.get("provenance")

    if not isinstance(provenance, dict):
        raise AuthoringError(
            f"{object_id} must include provenance"
        )

    transformation = provenance.get("transformation")

    if not isinstance(transformation, dict):
        raise AuthoringError(
            f"{object_id} must include "
            "provenance.transformation"
        )

    if "run_id" in transformation:
        raise AuthoringError(
            f"AI supplied provenance run_id for {object_id}"
        )

    if not str(
        transformation.get("method", "")
    ).startswith("llm_"):
        raise AuthoringError(
            f"LLM transformation method required for {object_id}"
        )

    transformation["run_id"] = run_id
    document.setdefault("schema_version", "1.0")

    verify_evidence(document, sources)

    relative = derive_path(kind, object_id)
    destination = backend / relative

    if action == "create":
        if object_id in existing or destination.exists():
            raise AuthoringError(
                f"create target already exists: {object_id}"
            )

        document["revision"] = 1
        document["created_at"] = timestamp
        classification = "CREATE"

    else:
        if object_id not in existing:
            raise AuthoringError(
                f"update target does not exist: {object_id}"
            )

        old_path, previous = existing[object_id]
        expected_hash = operation.get(
            "expected_content_hash"
        )

        if expected_hash != previous.get("content_hash"):
            raise AuthoringError(
                f"optimistic concurrency failure for {object_id}"
            )

        if (
            old_path.name != relative.name
            or old_path.parent.name != relative.parent.name
        ):
            raise AuthoringError(
                "derived path differs from existing path "
                f"for {object_id}: {old_path}"
            )

        document["revision"] = int(
            previous["revision"]
        ) + 1

        document["created_at"] = previous["created_at"]
        classification = "UPDATE"

    document["updated_at"] = timestamp
    document["content_hash"] = content_hash(document)

    validate_object(document)

    return classification, relative, document


def generation_run(
    transaction: dict[str, Any],
    run_id: str,
    timestamp: str,
    results: list[
        tuple[str, Path, dict[str, Any]]
    ],
) -> dict[str, Any]:
    """Create the authoritative generation-run record."""

    outputs = {
        "created": [],
        "updated": [],
        "unchanged": [],
    }

    for classification, _, document in results:
        if classification == "CREATE":
            outputs["created"].append(document["id"])
        elif classification == "UPDATE":
            outputs["updated"].append(document["id"])
        else:
            outputs["unchanged"].append(document["id"])

    return {
        "schema_version": "1.0",
        "id": run_id,
        "kind": "generation_run",
        "created_at": timestamp,
        "generator": {
            "type": "chat_ai",
            "model": "unspecified",
            "prompt_version": "authoring-task-1.0",
        },
        "operation": "incremental_extract",
        "inputs": [
            {
                "source_packet_hash": transaction[
                    "source_packet_hash"
                ],
                "transaction_id": transaction[
                    "transaction_id"
                ],
            }
        ],
        "existing_context": {
            "optimistic_concurrency": True,
            "registered_source_required": True,
        },
        "outputs": outputs,
        "unresolved": transaction.get(
            "unresolved",
            [],
        ),
        "quality": {
            "candidate_only": True,
            "staged_validation": True,
        },
        "warnings": [],
    }


def validate_staged(staged_content: Path) -> None:
    """Run the existing validator against the staged tree."""

    with tempfile.TemporaryDirectory(
        prefix="authoring-validation-"
    ) as temporary_directory:
        root = Path(temporary_directory)

        shutil.copytree(
            staged_content,
            root / "content",
        )

        (root / "scripts").mkdir()

        shutil.copy2(
            ROOT / "scripts" / "validate_content.py",
            root / "scripts" / "validate_content.py",
        )

        result = subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                str(root / "scripts" / "validate_content.py"),
            ],
            cwd=root,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        if result.returncode:
            details = (
                result.stderr.strip()
                or result.stdout.strip()
            )

            raise AuthoringError(
                "existing content validation failed:\n"
                f"{details}"
            )


def transactional_write(
    backend: Path,
    writes: list[tuple[Path, dict[str, Any]]],
) -> None:
    """Replace files with best-effort rollback on failure."""

    backups: dict[Path, bytes | None] = {}

    try:
        for relative, document in writes:
            destination = backend / relative

            backups[destination] = (
                destination.read_bytes()
                if destination.exists()
                else None
            )

            destination.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                newline="\n",
                dir=destination.parent,
                delete=False,
            ) as handle:
                yaml.safe_dump(
                    document,
                    handle,
                    sort_keys=False,
                    allow_unicode=True,
                )
                temporary = Path(handle.name)

            os.replace(temporary, destination)

    except Exception:
        for destination, previous in backups.items():
            try:
                if previous is None:
                    destination.unlink(missing_ok=True)
                else:
                    destination.write_bytes(previous)
            except OSError:
                pass

        raise


def command_apply(args: argparse.Namespace) -> None:
    """Validate, preview, or apply one transaction."""

    backend = require_backend(args.backend)
    transaction = read_yaml(args.transaction)
    validate_envelope(transaction)

    packet = read_yaml(args.packet)
    actual_packet_hash = packet_hash(packet)

    if actual_packet_hash != packet.get("packet_hash"):
        raise AuthoringError(
            "packet hash does not match packet contents"
        )

    if (
        packet["packet_hash"]
        != transaction["source_packet_hash"]
    ):
        raise AuthoringError(
            "transaction source_packet_hash does not "
            "match the supplied packet"
        )

    existing = load_objects(backend)
    sources = require_registered_source(
        packet,
        existing,
    )

    run_id = (
        "generation."
        + sha256(transaction["transaction_id"])[:16]
    )

    timestamp = now_utc()

    results = [
        enrich_operation(
            operation,
            existing,
            sources,
            run_id,
            timestamp,
            backend,
        )
        for operation in transaction["operations"]
    ]

    run = generation_run(
        transaction,
        run_id,
        timestamp,
        results,
    )

    validate_object(run)

    run_path = derive_path(
        "generation_run",
        run_id,
    )

    writes = [
        (relative, document)
        for _, relative, document in results
    ]

    writes.append((run_path, run))

    with tempfile.TemporaryDirectory(
        prefix="authoring-stage-"
    ) as temporary_directory:
        temporary_root = Path(temporary_directory)
        staged_content = temporary_root / "content"

        shutil.copytree(
            backend / "content",
            staged_content,
        )

        for relative, document in writes:
            target = temporary_root / relative
            write_yaml(target, document)

        validate_staged(staged_content)

    for classification, relative, document in results:
        references = [
            (
                f"{reference['source_id']}/"
                f"{reference['fragment_id']}"
            )
            for reference in document[
                "provenance"
            ]["sources"]
        ]

        print(
            f"{classification} "
            f"{relative.as_posix()} "
            f"[{', '.join(references)}]"
        )

        unsupported = document.get(
            "grounding",
            {},
        ).get(
            "unsupported_claims",
            [],
        )

        if unsupported:
            print(
                "  unsupported: "
                + "; ".join(unsupported)
            )

    print(
        f"CREATE {run_path.as_posix()} "
        "[generation run]"
    )

    print(
        f"[authoring] registered source: "
        f"{packet['source']['id']}"
    )

    if args.dry_run:
        print(
            "[authoring] dry run only; backend unchanged"
        )
        return

    transactional_write(backend, writes)

    print(
        f"[authoring] applied {len(writes)} file(s); "
        "validation completed before write and rollback "
        "is attempted on failure; no commit or publication "
        "performed"
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the Increment 1 command-line interface."""

    parser = argparse.ArgumentParser(
        description=__doc__,
    )

    commands = parser.add_subparsers(
        dest="command",
        required=True,
    )

    ingest = commands.add_parser(
        "ingest",
        help=(
            "create a deterministic packet from "
            "UTF-8 text"
        ),
    )

    ingest.add_argument(
        "--input",
        type=Path,
        required=True,
    )

    ingest.add_argument(
        "--source-id",
        required=True,
    )

    ingest.add_argument(
        "--source-type",
        choices=sorted(SOURCE_TYPES),
        required=True,
    )

    ingest.add_argument(
        "--source-metadata",
        choices=sorted(SOURCE_METADATA_POLICIES),
        default="forbidden",
    )

    ingest.add_argument(
        "--title",
        required=True,
    )

    ingest.add_argument(
        "--language",
        default="sv-SE",
    )

    ingest.add_argument(
        "--external-url",
    )

    ingest.add_argument(
        "--output",
        type=Path,
        required=True,
    )

    ingest.set_defaults(
        func=command_ingest,
    )

    prepare = commands.add_parser(
        "prepare",
        help="generate the bounded chat task",
    )

    prepare.add_argument(
        "--packet",
        type=Path,
        required=True,
    )

    prepare.add_argument(
        "--backend",
        type=Path,
        required=True,
    )

    prepare.add_argument(
        "--kinds",
        required=True,
    )

    prepare.add_argument(
        "--output",
        type=Path,
        required=True,
    )

    prepare.set_defaults(
        func=command_prepare,
    )

    apply_command = commands.add_parser(
        "apply",
        help=(
            "validate, preview, or transactionally "
            "apply a transaction"
        ),
    )

    apply_command.add_argument(
        "--transaction",
        type=Path,
        required=True,
    )

    apply_command.add_argument(
        "--packet",
        type=Path,
        required=True,
    )

    apply_command.add_argument(
        "--backend",
        type=Path,
        required=True,
    )

    apply_command.add_argument(
        "--dry-run",
        action="store_true",
    )

    apply_command.set_defaults(
        func=command_apply,
    )

    return parser


def main() -> int:
    """Run the selected authoring subcommand."""

    args = build_parser().parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AuthoringError as error:
        print(
            f"authoring failed: {error}",
            file=sys.stderr,
        )
        raise SystemExit(1)
