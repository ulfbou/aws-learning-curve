"""Deterministic bounded learning-context and transaction engine."""
from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml
from jsonschema import Draft202012Validator

COLLECTIONS = {
    "source": "sources",
    "concept": "concepts",
    "competency": "competencies",
    "learning_unit": "learning-units",
    "question": "questions",
    "scenario": "scenarios",
    "procedure": "procedures",
    "misconception": "misconceptions",
    "generation_run": "generation-runs",
}
SYSTEM_FIELDS = {"revision", "created_at", "updated_at", "content_hash"}
REFERENCE_KEYS = {
    "target_id", "concept_id", "source_id", "fragment_id", "run_id",
    "prerequisite_ids", "concept_ids", "competency_ids", "learning_objectives",
    "prerequisite_competencies", "recommended_question_ids", "misconception_ids",
    "question_ids", "scenario_ids", "learning_unit_ids", "source_ids", "fragment_ids",
}
ID_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+){1,10}$")


class WorkflowError(RuntimeError):
    """A deterministic workflow failure."""


@dataclass(frozen=True)
class Record:
    object_id: str
    kind: str
    status: str | None
    path: Path
    data: dict[str, Any]
    file_sha256: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def semantic_hash(value: dict[str, Any]) -> str:
    semantic = {k: v for k, v in value.items() if k != "content_hash"}
    return hashlib.sha256(canonical_json(semantic).encode("utf-8")).hexdigest()


def load_repository(root: Path) -> dict[str, Record]:
    content = root / "content"
    records: dict[str, Record] = {}
    if not content.is_dir():
        raise WorkflowError(f"content directory not found: {content}")
    for path in sorted(content.rglob("*.yaml")):
        if path.name == "manifest.yaml":
            continue
        raw = path.read_bytes()
        try:
            parsed = yaml.safe_load(raw.decode("utf-8"))
        except (UnicodeDecodeError, yaml.YAMLError) as exc:
            raise WorkflowError(f"cannot load {path.relative_to(root)}: {exc}") from exc
        objects = parsed if isinstance(parsed, list) else [parsed]
        for obj in objects:
            if not isinstance(obj, dict) or not isinstance(obj.get("id"), str):
                continue
            object_id = obj["id"]
            if object_id in records:
                raise WorkflowError(f"duplicate semantic ID: {object_id}")
            records[object_id] = Record(
                object_id, str(obj.get("kind", "")), obj.get("status"), path, obj,
                hashlib.sha256(raw).hexdigest(),
            )
    return records


def aliases_for(records: dict[str, Record], root: Path) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for record in records.values():
        for alias in record.data.get("aliases", []) or []:
            aliases[str(alias)] = record.object_id
    manifest = root / "content" / "manifest.yaml"
    if manifest.is_file():
        data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        aliases.update({str(k): str(v) for k, v in (data.get("aliases") or {}).items()})
    return aliases


def iter_reference_ids(value: Any, key: str | None = None) -> Iterable[str]:
    if isinstance(value, dict):
        for child_key, child in value.items():
            yield from iter_reference_ids(child, child_key)
    elif isinstance(value, list):
        for child in value:
            yield from iter_reference_ids(child, key)
    elif key in REFERENCE_KEYS and isinstance(value, str) and ID_RE.match(value):
        yield value


def searchable_text(record: Record) -> str:
    return canonical_json(record.data).casefold()


def build_context(root: Path, request: dict[str, Any]) -> dict[str, Any]:
    records = load_repository(root)
    aliases = aliases_for(records, root)
    ids = [str(x) for x in request.get("ids", [])]
    ids += [aliases.get(str(x), str(x)) for x in request.get("aliases", [])]
    keywords = [str(x).casefold() for x in request.get("keywords", []) if str(x).strip()]
    tags = {str(x) for x in request.get("tags", [])}
    kinds = {str(x) for x in request.get("kinds", [])}
    statuses = {str(x) for x in request.get("statuses", [])}
    limit = int(request.get("max_objects", 20))
    if not 1 <= limit <= 100:
        raise WorkflowError("max_objects must be between 1 and 100")

    selected: set[str] = set()
    for object_id, record in records.items():
        exact = object_id in ids
        keyword_match = bool(keywords) and all(word in searchable_text(record) for word in keywords)
        tag_match = bool(tags) and bool(tags.intersection(record.data.get("tags", []) or []))
        if not (exact or keyword_match or tag_match):
            continue
        if kinds and record.kind not in kinds:
            continue
        if statuses and record.status not in statuses:
            continue
        selected.add(object_id)

    missing = sorted(set(ids) - set(records))
    direct: set[str] = set()
    if request.get("include_direct_relationships", True):
        for object_id in selected:
            direct.update(ref for ref in iter_reference_ids(records[object_id].data) if ref in records)
    ordered_primary = sorted(selected)
    ordered_related = sorted(direct - selected)
    ordered = (ordered_primary + ordered_related)[:limit]

    def packet(record: Record) -> dict[str, Any]:
        return {
            "id": record.object_id,
            "kind": record.kind,
            "status": record.status,
            "path": record.path.relative_to(root).as_posix(),
            "revision": record.data.get("revision"),
            "content_hash": record.data.get("content_hash"),
            "file_sha256": record.file_sha256,
            "content": record.data,
        }

    return {
        "schema_version": "1.0",
        "packet_type": "learning_context",
        "learning_goal": str(request.get("learning_goal", "")).strip(),
        "query": {
            "ids": ids, "keywords": request.get("keywords", []),
            "tags": sorted(tags), "kinds": sorted(kinds), "statuses": sorted(statuses),
            "include_direct_relationships": bool(request.get("include_direct_relationships", True)),
        },
        "matches": [packet(records[x]) for x in ordered_primary if x in ordered],
        "related_objects": [packet(records[x]) for x in ordered_related if x in ordered],
        "missing_ids": missing,
        "context_limits": {"maximum_objects": limit, "direct_relationships_only": True},
        "repository": {"root": str(root.resolve()), "object_count": len(records)},
    }


def load_schema(root: Path) -> dict[str, Any]:
    path = root / "schemas" / "learning-transaction.schema.json"
    if not path.is_file():
        raise WorkflowError(f"transaction schema not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def validate_transaction(root: Path, transaction: dict[str, Any]) -> None:
    errors = sorted(
        Draft202012Validator(load_schema(root)).iter_errors(transaction),
        key=lambda e: list(e.path),
    )
    if errors:
        rendered = "; ".join(
            f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}"
            for e in errors
        )
        raise WorkflowError(f"invalid transaction: {rendered}")


def target_path(root: Path, obj: dict[str, Any]) -> Path:
    kind = str(obj.get("kind", ""))
    object_id = str(obj.get("id", ""))
    collection = COLLECTIONS.get(kind)
    if collection is None:
        raise WorkflowError(f"unsupported kind: {kind}")
    if not ID_RE.match(object_id):
        raise WorkflowError(f"unsafe semantic ID: {object_id!r}")
    path = root / "content" / collection / f"{object_id}.yaml"
    resolved_parent = path.parent.resolve()
    content_root = (root / "content").resolve()
    if content_root != resolved_parent and content_root not in resolved_parent.parents:
        raise WorkflowError(f"derived path escapes content root: {path}")
    return path


def enrich(
    operation: dict[str, Any],
    current: Record | None,
    now: str,
) -> dict[str, Any]:
    proposed = copy.deepcopy(operation["content"])
    proposed["id"] = operation["id"]
    proposed["kind"] = operation["kind"]
    for field in SYSTEM_FIELDS:
        proposed.pop(field, None)
    if current is None:
        proposed["revision"] = 1
        proposed["created_at"] = now
    else:
        proposed["revision"] = int(current.data.get("revision", 0)) + 1
        proposed["created_at"] = current.data.get("created_at", now)
    proposed["updated_at"] = now
    proposed["content_hash"] = semantic_hash(proposed)
    return proposed


def plan_transaction(
    root: Path,
    transaction: dict[str, Any],
) -> tuple[dict[str, Any], list[tuple[Path, bytes]]]:
    validate_transaction(root, transaction)
    records = load_repository(root)
    writes: list[tuple[Path, bytes]] = []
    changes = {"created": [], "updated": [], "unchanged": []}
    now = utc_now()
    seen: set[str] = set()

    for operation in transaction["operations"]:
        object_id = operation["id"]
        if object_id in seen:
            raise WorkflowError(
                f"transaction contains duplicate operation for {object_id}"
            )
        seen.add(object_id)
        action = operation["action"]
        current = records.get(object_id)

        if action == "unchanged":
            if current is None:
                raise WorkflowError(
                    f"unchanged target does not exist: {object_id}"
                )
            changes["unchanged"].append(object_id)
            continue

        if action == "create" and current is not None:
            raise WorkflowError(f"create target already exists: {object_id}")

        if action == "update":
            if current is None:
                raise WorkflowError(
                    f"update target does not exist: {object_id}"
                )
            if operation.get("expected_revision") != current.data.get("revision"):
                raise WorkflowError(f"revision conflict for {object_id}")
            if (
                operation.get("expected_content_hash")
                != current.data.get("content_hash")
            ):
                raise WorkflowError(f"content hash conflict for {object_id}")
            if operation["kind"] != current.kind:
                raise WorkflowError(f"kind cannot change for {object_id}")

        enriched = enrich(operation, current, now)
        path = target_path(root, enriched)

        if current is not None and path.resolve() != current.path.resolve():
            raise WorkflowError(
                f"derived path differs from current repository path for {object_id}"
            )

        payload = yaml.safe_dump(
            enriched,
            allow_unicode=True,
            sort_keys=False,
        ).encode("utf-8")

        writes.append((path, payload))
        changes["created" if action == "create" else "updated"].append(object_id)

    result = {
        "schema_version": "1.0",
        "operation": "apply",
        "result": "planned",
        "learning_goal": transaction["learning_goal"],
        "changes": changes,
        "warnings": [],
        "next_actions": ["review the proposed repository changes"],
    }
    return result, writes


def write_with_rollback(
    writes: list[tuple[Path, bytes]],
    validator,
) -> None:
    backups: dict[Path, bytes | None] = {}
    try:
        for path, payload in writes:
            backups[path] = path.read_bytes() if path.exists() else None
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(path.name + ".tmp")
            temporary.write_bytes(payload)
            temporary.replace(path)
        validator()
    except Exception:
        for path, previous in reversed(list(backups.items())):
            if previous is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(previous)
        raise


def run_repository_validator(root: Path) -> None:
    script = root / "scripts" / "validate_content.py"
    if not script.is_file():
        raise WorkflowError(f"repository validator not found: {script}")

    completed = subprocess.run(
        [sys.executable, str(script)],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise WorkflowError(f"repository validation failed: {detail}")


def dry_run(
    root: Path,
    transaction: dict[str, Any],
) -> dict[str, Any]:
    result, writes = plan_transaction(root, transaction)

    with tempfile.TemporaryDirectory(
        prefix="learning-workflow-"
    ) as directory:
        staged = Path(directory) / "workspace"
        staged.mkdir()

        for name in ("content", "schemas", "scripts"):
            source = root / name
            if source.exists():
                shutil.copytree(source, staged / name)

        staged_result, staged_writes = plan_transaction(
            staged,
            transaction,
        )
        write_with_rollback(
            staged_writes,
            lambda: run_repository_validator(staged),
        )
        result["changes"] = staged_result["changes"]

    result["operation"] = "dry_run"
    result["result"] = "success"
    result["next_actions"] = [
        "review the dry-run",
        "apply the reviewed transaction",
    ]
    return result


def apply_transaction(
    root: Path,
    transaction: dict[str, Any],
) -> dict[str, Any]:
    result, writes = plan_transaction(root, transaction)
    write_with_rollback(
        writes,
        lambda: run_repository_validator(root),
    )
    result["result"] = "success"
    result["next_actions"] = [
        "review the changed learning artifacts",
        "use them in a short study session",
        "record the unresolved point",
    ]
    return result
