"""Shared deterministic primitives for bounded authoring transactions."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, RefResolver


ROOT = Path(__file__).resolve().parents[1]

ID_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+){1,10}$")

SYSTEM_FIELDS = {
    "revision",
    "created_at",
    "updated_at",
    "content_hash",
}

KIND_PATHS = {
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

SCHEMA_FILES = {
    kind: f"{kind.replace('_', '-')}.schema.json"
    for kind in KIND_PATHS
}


class AuthoringError(RuntimeError):
    """Raised when an authoring invariant is violated."""


def canonical_bytes(value: Any) -> bytes:
    """Return deterministic UTF-8 JSON bytes for hashing."""

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sha256(value: bytes | str) -> str:
    """Return an unprefixed lowercase SHA-256 digest."""

    if isinstance(value, str):
        value = value.encode("utf-8")

    return hashlib.sha256(value).hexdigest()


def content_hash(document: dict[str, Any]) -> str:
    """Compute a content hash without recursively hashing content_hash."""

    clean = dict(document)
    clean.pop("content_hash", None)
    return sha256(canonical_bytes(clean))


def packet_hash(packet: dict[str, Any]) -> str:
    """Compute the authoritative prefixed packet hash."""

    clean = dict(packet)
    clean.pop("packet_hash", None)
    return "sha256:" + sha256(canonical_bytes(clean))


def read_yaml(path: Path) -> dict[str, Any]:
    """Read one YAML mapping."""

    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise AuthoringError(
            f"cannot read YAML {path}: {error}"
        ) from error

    if not isinstance(value, dict):
        raise AuthoringError(
            f"expected one YAML mapping in {path}"
        )

    return value


def write_yaml(path: Path, value: dict[str, Any]) -> None:
    """Write deterministic human-readable YAML."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            value,
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
        newline="\n",
    )


def normalize_text(text: str) -> str:
    """Normalize whitespace for comparison and fingerprinting."""

    return " ".join(text.split())


def split_fragments(text: str) -> list[tuple[int, int, str]]:
    """Split text on blank lines while retaining character offsets."""

    fragments: list[tuple[int, int, str]] = []
    cursor = 0
    separators = list(re.finditer(r"(?:\r?\n){2,}", text))

    for separator in [*separators, None]:
        end = separator.start() if separator is not None else len(text)
        exact = text[cursor:end]

        if normalize_text(exact):
            fragments.append((cursor, end, exact))

        cursor = separator.end() if separator is not None else len(text)

    return fragments


def derive_path(kind: str, object_id: str) -> Path:
    """Derive a safe repository-relative path from kind and semantic ID."""

    if kind not in KIND_PATHS:
        raise AuthoringError(
            f"unsupported kind: {kind}"
        )

    if (
        not isinstance(object_id, str)
        or not ID_RE.fullmatch(object_id)
        or len(object_id) > 128
    ):
        raise AuthoringError(
            f"invalid {kind} object id: {object_id}"
        )

    relative = (
        Path("content")
        / KIND_PATHS[kind]
        / f"{object_id}.yaml"
    )

    if relative.is_absolute() or ".." in relative.parts:
        raise AuthoringError(
            f"unsafe derived path: {relative}"
        )

    return relative


def load_objects(
    backend: Path,
) -> dict[str, tuple[Path, dict[str, Any]]]:
    """Load backend content objects indexed by semantic ID."""

    objects: dict[str, tuple[Path, dict[str, Any]]] = {}

    for path in sorted((backend / "content").glob("**/*.yaml")):
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
        documents = value if isinstance(value, list) else [value]

        for document in documents:
            if (
                isinstance(document, dict)
                and isinstance(document.get("id"), str)
            ):
                objects[document["id"]] = (path, document)

    return objects


def schema_validator(kind: str) -> Draft202012Validator:
    """Create a schema validator for a repository object kind."""

    schema_root = ROOT / "schemas"

    if kind not in SCHEMA_FILES:
        raise AuthoringError(
            f"no schema for kind: {kind}"
        )

    schemas: dict[str, Any] = {}

    for path in schema_root.glob("*.schema.json"):
        schema = json.loads(path.read_text(encoding="utf-8"))
        schemas[path.name] = schema

        if "$id" in schema:
            schemas[schema["$id"]] = schema

    schema_name = SCHEMA_FILES[kind]

    if schema_name not in schemas:
        raise AuthoringError(
            f"schema file is missing for kind {kind}: {schema_name}"
        )

    root_schema = schemas[schema_name]
    resolver = RefResolver.from_schema(
        root_schema,
        store=schemas,
    )

    return Draft202012Validator(
        root_schema,
        resolver=resolver,
    )


def validate_object(document: dict[str, Any]) -> None:
    """Validate one completed repository object."""

    kind = str(document.get("kind"))
    validator = schema_validator(kind)

    errors = sorted(
        validator.iter_errors(document),
        key=lambda error: list(error.path),
    )

    if not errors:
        return

    details = "; ".join(
        (
            f"{'/'.join(map(str, error.path)) or '<root>'}: "
            f"{error.message}"
        )
        for error in errors[:12]
    )

    raise AuthoringError(
        f"schema validation failed for "
        f"{document.get('id')}: {details}"
    )
