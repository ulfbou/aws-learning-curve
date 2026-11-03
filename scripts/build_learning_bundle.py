"""
Build the public browser bundle from canonical learning content.

Registered source objects remain available to internal tooling and grounding,
but they are not public learning content and are never serialized here.
"""

from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DATA = ROOT / "public" / "data"

SOURCE_PATTERNS = (
    "content/sources/**/*.yaml",
)

LEARNING_OBJECT_PATTERNS = (
    "content/concepts/**/*.yaml",
    "content/competencies/**/*.yaml",
    "content/learning-units/**/*.yaml",
    "content/questions/**/*.yaml",
    "content/scenarios/**/*.yaml",
    "content/procedures/**/*.yaml",
    "content/misconceptions/**/*.yaml",
)

COLLECTIONS = {
    "concepts": {},
    "competencies": {},
    "learningUnits": {},
    "questions": {},
    "scenarios": {},
    "procedures": {},
    "misconceptions": {},
    "sources": {},
}

KIND_MAP = {
    "concept": "concepts",
    "competency": "competencies",
    "learning_unit": "learningUnits",
    "question": "questions",
    "scenario": "scenarios",
    "procedure": "procedures",
    "misconception": "misconceptions",
}


def load_yaml_glob(pattern: str) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []

    for path in ROOT.glob(pattern):
        if not path.is_file() or path.name == ".gitkeep":
            continue

        document = yaml.safe_load(
            path.read_text(encoding="utf-8")
        )

        if document is None:
            continue

        if isinstance(document, list):
            objects.extend(
                value
                for value in document
                if isinstance(value, dict)
            )
        elif isinstance(document, dict):
            objects.append(document)

    return objects


def sha256_hex(value: str) -> str:
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


def add_index(
    index: dict[str, list[str]],
    key: str | None,
    object_id: str,
) -> None:
    if not key:
        return

    values = index.setdefault(key, [])

    if object_id not in values:
        values.append(object_id)


def main() -> None:
    print("Building public learning bundle")

    registered_sources: list[dict[str, Any]] = []
    for pattern in SOURCE_PATTERNS:
        registered_sources.extend(
            load_yaml_glob(pattern)
        )

    learning_objects: list[dict[str, Any]] = []
    for pattern in LEARNING_OBJECT_PATTERNS:
        learning_objects.extend(
            load_yaml_glob(pattern)
        )

    public_objects = [
        value
        for value in learning_objects
        if value.get("status") == "published"
    ]

    for value in public_objects:
        unsupported = (
            value
            .get("grounding", {})
            .get("unsupported_claims")
        )

        if unsupported:
            raise SystemExit(
                f"Unsupported claims {value['id']}"
            )

    public_ids = {
        value["id"]
        for value in public_objects
    }

    alias_map: dict[str, str] = {}

    for value in public_objects:
        for alias in value.get("aliases", []) or []:
            alias_map[str(alias)] = value["id"]

    manifest_path = ROOT / "content" / "manifest.yaml"
    manifest: dict[str, Any] = {}

    if manifest_path.exists():
        manifest = (
            yaml.safe_load(
                manifest_path.read_text(
                    encoding="utf-8"
                )
            )
            or {}
        )

        for alias, target in (
            manifest.get("aliases", {}) or {}
        ).items():
            if target in public_ids:
                alias_map[str(alias)] = str(target)

    collections = {
        key: {}
        for key in COLLECTIONS
    }

    for value in public_objects:
        collection = KIND_MAP.get(value.get("kind"))

        if collection:
            collections[collection][value["id"]] = value

    indexes: dict[str, Any] = {
        "byTag": {},
        "byCompetency": {},
        "byConcept": {},
        "byDifficulty": {},
        "byMisconception": {},
        "prerequisites": {},
        "contrasts": [],
    }

    for value in public_objects:
        object_id = value["id"]

        for tag in value.get("tags", []):
            add_index(
                indexes["byTag"],
                tag,
                object_id,
            )

        if value.get("difficulty"):
            add_index(
                indexes["byDifficulty"],
                value["difficulty"],
                object_id,
            )

        for concept_id in value.get(
            "concept_ids",
            [],
        ):
            add_index(
                indexes["byConcept"],
                concept_id,
                object_id,
            )

        for competency_id in value.get(
            "competency_ids",
            [],
        ):
            add_index(
                indexes["byCompetency"],
                competency_id,
                object_id,
            )

        for misconception_id in value.get(
            "misconception_ids",
            [],
        ):
            add_index(
                indexes["byMisconception"],
                misconception_id,
                object_id,
            )

        prerequisites = value.get(
            "prerequisite_ids"
        )

        if prerequisites:
            indexes["prerequisites"][
                object_id
            ] = prerequisites

        if (
            value.get("kind") == "concept"
            and value.get("concept_type")
            == "contrast"
        ):
            indexes["contrasts"].append(
                object_id
            )

    generated_at = manifest.get(
        "generated_at",
        datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat(),
    )
    content_version = manifest.get(
        "content_version",
        "2026-11-01.1",
    )

    bundle = {
        "schemaVersion": "1.0",
        "contentVersion": content_version,
        "generatedAt": generated_at,
        "aliasMap": alias_map,
        "concepts": collections["concepts"],
        "competencies": collections[
            "competencies"
        ],
        "learningUnits": collections[
            "learningUnits"
        ],
        "questions": collections["questions"],
        "scenarios": collections["scenarios"],
        "procedures": collections["procedures"],
        "misconceptions": collections[
            "misconceptions"
        ],
        "sources": {},
        "indexes": indexes,
        "manifest": {
            "contentVersion": content_version,
            "generatedAt": generated_at,
            "counts": {
                key: len(value)
                for key, value
                in collections.items()
            },
            "publishedOnly": True,
            "privateExcluded": True,
            "registeredSourcesExcluded": True,
        },
    }

    PUBLIC_DATA.mkdir(
        parents=True,
        exist_ok=True,
    )

    bundle_path = (
        PUBLIC_DATA
        / "learning-bundle.json"
    )

    bundle_path.write_text(
        json.dumps(
            bundle,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    bundle_text = bundle_path.read_text(
        encoding="utf-8"
    )
    bundle_hash = sha256_hex(bundle_text)

    public_manifest = {
        "schemaVersion": "1.0",
        "contentVersion": content_version,
        "generatedAt": generated_at,
        "bundlePath": (
            "public/data/learning-bundle.json"
        ),
        "bundleHash": bundle_hash,
        "bundleSizeBytes": (
            bundle_path.stat().st_size
        ),
        "perObjectHashes": {
            value["id"]: (
                value.get("content_hash")
                or sha256_hex(
                    json.dumps(
                        value,
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                )
            )
            for value in public_objects
        },
        "aliasMap": alias_map,
        "releaseInvariants": [
            "Private learner state is excluded from public/data.",
            "Registered source objects and source fragments are excluded from the public bundle.",
            "Only published learning objects are serialized.",
            "No published object may reference an unpublished learning object.",
            "No published object may contain unsupported claims.",
            "All public references resolve after alias expansion.",
            "Bundle and manifest hashes match.",
        ],
    }

    (
        PUBLIC_DATA
        / "learning-bundle.manifest.json"
    ).write_text(
        json.dumps(
            public_manifest,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(
        "Public bundle built: "
        f"{len(public_objects)} learning objects, "
        f"{len(registered_sources)} registered sources excluded, "
        f"hash {bundle_hash[:12]}..."
    )


if __name__ == "__main__":
    main()
