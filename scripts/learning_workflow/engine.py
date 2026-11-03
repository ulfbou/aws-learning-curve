"""Deterministic bounded learning-context and prepared-plan engine."""
from __future__ import annotations

import base64
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
HASH_EXCLUDED_FIELDS = {
    "revision",
    "created_at",
    "updated_at",
    "content_hash",
}
REFERENCE_KEYS = {
    "target_id", "concept_id", "source_id", "fragment_id", "run_id",
    "prerequisite_ids", "concept_ids", "competency_ids", "learning_objectives",
    "prerequisite_competencies", "recommended_question_ids", "misconception_ids",
    "question_ids", "scenario_ids", "learning_unit_ids", "source_ids", "fragment_ids",
}
ID_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+){1,10}$")
HEX_RE = re.compile(r"^[a-f0-9]{64}$")


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


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def semantic_hash(value: dict[str, Any]) -> str:
    semantic = {
        key: item
        for key, item in value.items()
        if key not in HASH_EXCLUDED_FIELDS
    }
    return sha256_bytes(
        canonical_json(semantic).encode("utf-8")
    )


def load_repository(content_workspace: Path) -> dict[str, Record]:
    content = content_workspace / "content"
    if not content.is_dir():
        raise WorkflowError(f"content directory not found: {content}")
    records: dict[str, Record] = {}
    for path in sorted(content.rglob("*.yaml")):
        if path.name == "manifest.yaml":
            continue
        raw = path.read_bytes()
        try:
            parsed = yaml.safe_load(raw.decode("utf-8"))
        except (UnicodeDecodeError, yaml.YAMLError) as exc:
            raise WorkflowError(f"cannot load {path.relative_to(content_workspace)}: {exc}") from exc
        for obj in parsed if isinstance(parsed, list) else [parsed]:
            if not isinstance(obj, dict) or not isinstance(obj.get("id"), str):
                continue
            object_id = obj["id"]
            if object_id in records:
                raise WorkflowError(f"duplicate semantic ID: {object_id}")
            records[object_id] = Record(
                object_id, str(obj.get("kind", "")), obj.get("status"), path, obj,
                sha256_bytes(raw),
            )
    return records


def aliases_for(records: dict[str, Record], content_workspace: Path) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for record in records.values():
        for alias in record.data.get("aliases", []) or []:
            aliases[str(alias)] = record.object_id
    manifest = content_workspace / "content" / "manifest.yaml"
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


def build_context(content_workspace: Path, request: dict[str, Any]) -> dict[str, Any]:
    records = load_repository(content_workspace)
    aliases = aliases_for(records, content_workspace)
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
        text = canonical_json(record.data).casefold()
        matched = (
            object_id in ids
            or (bool(keywords) and all(word in text for word in keywords))
            or (bool(tags) and bool(tags.intersection(record.data.get("tags", []) or [])))
        )
        if matched and (not kinds or record.kind in kinds) and (not statuses or record.status in statuses):
            selected.add(object_id)

    direct: set[str] = set()
    if request.get("include_direct_relationships", True):
        for object_id in selected:
            direct.update(ref for ref in iter_reference_ids(records[object_id].data) if ref in records)
    primary = sorted(selected)
    related = sorted(direct - selected)
    allowed = set((primary + related)[:limit])

    def packet(record: Record) -> dict[str, Any]:
        return {
            "id": record.object_id,
            "kind": record.kind,
            "status": record.status,
            "path": record.path.relative_to(content_workspace).as_posix(),
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
            "ids": ids,
            "keywords": request.get("keywords", []),
            "tags": sorted(tags),
            "kinds": sorted(kinds),
            "statuses": sorted(statuses),
            "include_direct_relationships": bool(request.get("include_direct_relationships", True)),
        },
        "matches": [packet(records[x]) for x in primary if x in allowed],
        "related_objects": [packet(records[x]) for x in related if x in allowed],
        "missing_ids": sorted(set(ids) - set(records)),
        "context_limits": {"maximum_objects": limit, "direct_relationships_only": True},
        "repository": {"content_workspace": str(content_workspace.resolve()), "object_count": len(records)},
    }


def load_transaction_schema(tooling_root: Path) -> dict[str, Any]:
    path = tooling_root / "schemas" / "learning-transaction.schema.json"
    if not path.is_file():
        raise WorkflowError(f"transaction schema not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def validate_transaction(tooling_root: Path, transaction: dict[str, Any]) -> None:
    errors = sorted(
        Draft202012Validator(load_transaction_schema(tooling_root)).iter_errors(transaction),
        key=lambda error: list(error.path),
    )
    if errors:
        rendered = "; ".join(
            f"{'/'.join(map(str, error.path)) or '<root>'}: {error.message}"
            for error in errors
        )
        raise WorkflowError(f"invalid transaction: {rendered}")


def relative_target(obj: dict[str, Any]) -> Path:
    kind = str(obj.get("kind", ""))
    object_id = str(obj.get("id", ""))
    collection = COLLECTIONS.get(kind)
    if collection is None:
        raise WorkflowError(f"unsupported kind: {kind}")
    if not ID_RE.match(object_id):
        raise WorkflowError(f"unsafe semantic ID: {object_id!r}")
    return Path("content") / collection / f"{object_id}.yaml"


def target_path(content_workspace: Path, relative: str) -> Path:
    path = content_workspace / Path(relative)
    resolved = path.resolve()
    content_root = (content_workspace / "content").resolve()
    if content_root not in resolved.parents:
        raise WorkflowError(f"prepared path escapes content root: {relative}")
    return path


def transaction_for_run_id(transaction: dict[str, Any]) -> dict[str, Any]:
    """Return the semantic transaction without any AI-supplied run identifier."""
    cleaned = copy.deepcopy(transaction)
    for operation in cleaned.get("operations", []):
        content = operation.get("content")
        if not isinstance(content, dict):
            continue
        provenance = content.get("provenance")
        if not isinstance(provenance, dict):
            continue
        transformation = provenance.get("transformation")
        if isinstance(transformation, dict):
            transformation.pop("run_id", None)
    return cleaned


def generation_run_id(transaction: dict[str, Any]) -> str:
    digest = sha256_bytes(
        canonical_json(transaction_for_run_id(transaction)).encode("utf-8")
    )
    return f"generation.{digest[:16]}"


def assign_run_id(proposed: dict[str, Any], run_id: str) -> None:
    provenance = proposed.setdefault("provenance", {})
    if not isinstance(provenance, dict):
        raise WorkflowError("provenance must be an object")
    transformation = provenance.setdefault("transformation", {})
    if not isinstance(transformation, dict):
        raise WorkflowError("provenance.transformation must be an object")
    transformation.setdefault("method", "llm_extraction")
    transformation.setdefault("fidelity", "generated")
    transformation["run_id"] = run_id


def enrich(
    operation: dict[str, Any],
    current: Record | None,
    prepared_at: str,
    run_id: str,
) -> dict[str, Any]:
    proposed = copy.deepcopy(operation["content"])
    proposed["id"] = operation["id"]
    proposed["kind"] = operation["kind"]
    for field in SYSTEM_FIELDS:
        proposed.pop(field, None)
    assign_run_id(proposed, run_id)
    if current is None:
        proposed["revision"] = 1
        proposed["created_at"] = prepared_at
    else:
        proposed["revision"] = int(current.data.get("revision", 0)) + 1
        proposed["created_at"] = current.data.get("created_at", prepared_at)
    proposed["updated_at"] = prepared_at
    proposed["content_hash"] = semantic_hash(proposed)
    return proposed


def prepared_operation(
    obj: dict[str, Any],
    action: str,
    expected_file_sha256: str | None,
) -> dict[str, Any]:
    payload = yaml.safe_dump(
        obj,
        allow_unicode=True,
        sort_keys=False,
    ).encode("utf-8")
    return {
        "action": action,
        "id": obj["id"],
        "kind": obj["kind"],
        "path": relative_target(obj).as_posix(),
        "expected_file_sha256": expected_file_sha256,
        "payload_sha256": sha256_bytes(payload),
        "content_hash": semantic_hash(obj),
        "payload_base64": base64.b64encode(payload).decode("ascii"),
    }


def prepare_transaction(
    tooling_root: Path,
    content_workspace: Path,
    transaction: dict[str, Any],
    prepared_at: str | None = None,
) -> dict[str, Any]:
    validate_transaction(tooling_root, transaction)
    records = load_repository(content_workspace)
    timestamp = prepared_at or utc_now()
    run_id = generation_run_id(transaction)
    if run_id in records:
        raise WorkflowError(f"generation run already exists: {run_id}")

    operations: list[dict[str, Any]] = []
    changes = {"created": [], "updated": [], "unchanged": []}
    seen: set[str] = set()

    for operation in transaction["operations"]:
        object_id = operation["id"]
        if object_id in seen:
            raise WorkflowError(f"transaction contains duplicate operation for {object_id}")
        seen.add(object_id)
        action = operation["action"]
        current = records.get(object_id)
        if action == "unchanged":
            if current is None:
                raise WorkflowError(f"unchanged target does not exist: {object_id}")
            changes["unchanged"].append(object_id)
            continue
        if action == "create" and current is not None:
            raise WorkflowError(f"create target already exists: {object_id}")
        if action == "update":
            if current is None:
                raise WorkflowError(f"update target does not exist: {object_id}")
            if operation.get("expected_revision") != current.data.get("revision"):
                raise WorkflowError(f"revision conflict for {object_id}")
            if operation.get("expected_content_hash") != current.data.get("content_hash"):
                raise WorkflowError(f"content hash conflict for {object_id}")
            if operation["kind"] != current.kind:
                raise WorkflowError(f"kind cannot change for {object_id}")

        enriched = enrich(operation, current, timestamp, run_id)
        relative = relative_target(enriched).as_posix()
        if current is not None and (content_workspace / relative).resolve() != current.path.resolve():
            raise WorkflowError(
                f"derived path differs from current repository path for {object_id}"
            )
        operations.append(
            prepared_operation(
                enriched,
                action,
                current.file_sha256 if current else None,
            )
        )
        changes["created" if action == "create" else "updated"].append(object_id)

    run_inputs: list[dict[str, Any]] = [
        {"learning_goal": transaction["learning_goal"]}
    ]
    if transaction.get("context_created_from"):
        run_inputs[0]["context_created_from"] = transaction["context_created_from"]
    generation_run = {
        "schema_version": "1.0",
        "id": run_id,
        "kind": "generation_run",
        "created_at": timestamp,
        "generator": {
            "type": "chat_ai",
            "model": "unspecified",
            "prompt_version": "bounded-learning-v1",
        },
        "operation": "incremental_extract",
        "inputs": run_inputs,
        "outputs": copy.deepcopy(changes),
        "unresolved": [],
        "warnings": [],
    }
    operations.append(prepared_operation(generation_run, "create", None))

    plan = {
        "schema_version": "1.0",
        "plan_type": "prepared_learning_transaction",
        "prepared_at": timestamp,
        "learning_goal": transaction["learning_goal"],
        "generation_run_id": run_id,
        "changes": changes,
        "operations": operations,
    }
    plan["plan_sha256"] = sha256_bytes(canonical_json(plan).encode("utf-8"))
    return plan


def validate_prepared_plan(plan: dict[str, Any]) -> None:
    required = {
        "schema_version", "plan_type", "prepared_at", "learning_goal",
        "generation_run_id", "changes", "operations", "plan_sha256",
    }
    if set(plan) != required or plan.get("schema_version") != "1.0" or plan.get("plan_type") != "prepared_learning_transaction":
        raise WorkflowError("invalid prepared plan envelope")
    unsigned = {key: value for key, value in plan.items() if key != "plan_sha256"}
    if plan["plan_sha256"] != sha256_bytes(canonical_json(unsigned).encode("utf-8")):
        raise WorkflowError("prepared plan hash mismatch")
    if not isinstance(plan["operations"], list):
        raise WorkflowError("prepared plan operations must be an array")
    for operation in plan["operations"]:
        expected = {
            "action", "id", "kind", "path", "expected_file_sha256",
            "payload_sha256", "content_hash", "payload_base64",
        }
        if set(operation) != expected:
            raise WorkflowError("invalid prepared operation")
        if not HEX_RE.match(operation["payload_sha256"]) or not HEX_RE.match(operation["content_hash"]):
            raise WorkflowError("invalid prepared operation hash")
        try:
            payload = base64.b64decode(operation["payload_base64"], validate=True)
        except Exception as exc:
            raise WorkflowError("invalid prepared payload encoding") from exc
        if sha256_bytes(payload) != operation["payload_sha256"]:
            raise WorkflowError(f"prepared payload hash mismatch for {operation['id']}")


def planned_writes(content_workspace: Path, plan: dict[str, Any]) -> list[tuple[Path, bytes]]:
    validate_prepared_plan(plan)
    writes: list[tuple[Path, bytes]] = []
    for operation in plan["operations"]:
        path = target_path(content_workspace, operation["path"])
        current_hash = sha256_bytes(path.read_bytes()) if path.is_file() else None
        if current_hash != operation["expected_file_sha256"]:
            raise WorkflowError(f"stale prepared plan for {operation['id']}")
        payload = base64.b64decode(operation["payload_base64"], validate=True)
        writes.append((path, payload))
    return writes


def assemble_validation_workspace(tooling_root: Path, content_workspace: Path, target: Path) -> None:
    shutil.copytree(content_workspace / "content", target / "content")
    shutil.copytree(tooling_root / "schemas", target / "schemas")
    shutil.copytree(tooling_root / "scripts", target / "scripts")


def run_repository_validator(tooling_root: Path, content_workspace: Path) -> None:
    script = tooling_root / "scripts" / "validate_content.py"
    if not script.is_file():
        raise WorkflowError(f"repository validator not found: {script}")
    with tempfile.TemporaryDirectory(prefix="learning-validation-") as directory:
        staged = Path(directory) / "workspace"
        assemble_validation_workspace(tooling_root, content_workspace, staged)
        completed = subprocess.run(
            [sys.executable, "-X", "utf8", str(staged / "scripts" / "validate_content.py")],
            cwd=staged,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        if completed.returncode:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise WorkflowError(f"repository validation failed: {detail}")


def write_with_rollback(writes: list[tuple[Path, bytes]], validator) -> None:
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


def result_for(plan: dict[str, Any], operation: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "operation": operation,
        "result": "success",
        "prepared_at": plan["prepared_at"],
        "plan_sha256": plan["plan_sha256"],
        "learning_goal": plan["learning_goal"],
        "generation_run_id": plan["generation_run_id"],
        "changes": plan["changes"],
        "planned_outputs": [
            {
                "id": item["id"],
                "path": item["path"],
                "payload_sha256": item["payload_sha256"],
                "content_hash": item["content_hash"],
            }
            for item in plan["operations"]
        ],
        "warnings": [],
    }


def dry_run_prepared_plan(tooling_root: Path, content_workspace: Path, plan: dict[str, Any]) -> dict[str, Any]:
    writes = planned_writes(content_workspace, plan)
    with tempfile.TemporaryDirectory(prefix="learning-dry-run-") as directory:
        staged_content = Path(directory) / "backend"
        shutil.copytree(content_workspace / "content", staged_content / "content")
        staged_writes = [
            (staged_content / path.relative_to(content_workspace), payload)
            for path, payload in writes
        ]
        write_with_rollback(
            staged_writes,
            lambda: run_repository_validator(tooling_root, staged_content),
        )
    result = result_for(plan, "dry_run")
    result["next_actions"] = ["review the dry-run", "execute this exact prepared plan"]
    return result


def apply_prepared_plan(tooling_root: Path, content_workspace: Path, plan: dict[str, Any]) -> dict[str, Any]:
    writes = planned_writes(content_workspace, plan)
    write_with_rollback(
        writes,
        lambda: run_repository_validator(tooling_root, content_workspace),
    )
    result = result_for(plan, "apply")
    result["next_actions"] = [
        "review the changed learning artifacts",
        "use them in a short study session",
        "record the unresolved point",
    ]
    return result

# Backward-compatible Python API retained for existing callers and tests.
def plan_transaction(root: Path, transaction: dict[str, Any]) -> tuple[dict[str, Any], list[tuple[Path, bytes]]]:
    plan = prepare_transaction(root, root, transaction)
    writes = planned_writes(root, plan)
    result = result_for(plan, "prepare")
    return result, writes


def dry_run(root: Path, transaction: dict[str, Any]) -> dict[str, Any]:
    plan = prepare_transaction(root, root, transaction)
    return dry_run_prepared_plan(root, root, plan)


def apply_transaction(root: Path, transaction: dict[str, Any]) -> dict[str, Any]:
    plan = prepare_transaction(root, root, transaction)
    return apply_prepared_plan(root, root, plan)
