"""Validate canonical AWS Learning Curve repository content."""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
ID_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+){1,10}$")
HASH_PATTERN = re.compile(r"^[a-f0-9]{64}$")
PATTERNS = (
    "content/sources/**/*.yaml",
    "content/concepts/**/*.yaml",
    "content/competencies/**/*.yaml",
    "content/learning-units/**/*.yaml",
    "content/questions/**/*.yaml",
    "content/scenarios/**/*.yaml",
    "content/procedures/**/*.yaml",
    "content/misconceptions/**/*.yaml",
    "content/generation-runs/**/*.yaml",
)
LEARNING_KINDS = {
    "concept", "competency", "learning_unit", "question", "scenario",
    "procedure", "misconception",
}


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_yaml_glob(pattern: str) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    for path in ROOT.glob(pattern):
        if not path.is_file() or path.name == ".gitkeep":
            continue
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if document is None:
            continue
        if isinstance(document, list):
            objects.extend(item for item in document if isinstance(item, dict))
        elif isinstance(document, dict):
            objects.append(document)
    return objects


def load_all() -> dict[str, dict[str, Any]]:
    objects: dict[str, dict[str, Any]] = {}
    for pattern in PATTERNS:
        for obj in load_yaml_glob(pattern):
            object_id = obj.get("id")
            if not isinstance(object_id, str):
                raise ValueError(f"Missing id in {pattern}")
            if object_id in objects:
                raise ValueError(f"Duplicate ID {object_id}")
            objects[object_id] = obj
    return objects


def duplicates(values: list[Any]) -> set[Any]:
    seen: set[Any] = set()
    repeated: set[Any] = set()
    for value in values:
        if value in seen:
            repeated.add(value)
        seen.add(value)
    return repeated


def validate_common(objects: dict[str, dict[str, Any]]) -> list[str]:
    failures: list[str] = []
    fragment_owners: dict[str, str] = {}
    for object_id, obj in objects.items():
        kind = obj.get("kind")
        if kind != "generation_run":
            for field in ("revision", "created_at", "updated_at", "content_hash"):
                if field not in obj:
                    failures.append(f"Missing {field} in {object_id}")
        if not ID_PATTERN.match(object_id) or len(object_id) > 128:
            failures.append(f"ID pattern fail {object_id}")
        if "content_hash" in obj and not HASH_PATTERN.match(str(obj["content_hash"])):
            failures.append(f"Bad hash {object_id}")
        if kind != "source":
            continue
        for fragment in obj.get("fragments", []) or []:
            fragment_id = fragment.get("id")
            if not isinstance(fragment_id, str):
                failures.append(f"Fragment missing id {object_id}")
                continue
            owner = fragment_owners.get(fragment_id)
            if owner is not None:
                failures.append(
                    f"Duplicate fragment ID {fragment_id} in {owner} and {object_id}"
                )
            fragment_owners[fragment_id] = object_id
            normalized = fragment.get("normalized_text")
            fingerprint = fragment.get("content_fingerprint")
            if not isinstance(normalized, str) or not isinstance(fingerprint, str):
                failures.append(f"Fragment missing normalized text/fingerprint {object_id}/{fragment_id}")
                continue
            expected = sha256(normalized)[:32]
            if fingerprint != expected:
                failures.append(f"Fragment fingerprint mismatch {object_id}/{fragment_id}")
    return failures


def validate_grounding(objects: dict[str, dict[str, Any]]) -> list[str]:
    failures: list[str] = []
    for object_id, obj in objects.items():
        if obj.get("kind") not in LEARNING_KINDS:
            continue
        provenance = obj.get("provenance")
        grounding = obj.get("grounding")
        if not isinstance(provenance, dict):
            continue
        source_grounded = bool(
            (provenance.get("verification") or {}).get("source_grounded")
        )
        sources = provenance.get("sources") or []
        pairs = [
            (item.get("source_id"), item.get("fragment_id"))
            for item in sources
            if isinstance(item, dict)
        ]
        if len(pairs) != len(sources) or any(not source or not fragment for source, fragment in pairs):
            failures.append(f"Invalid provenance citation {object_id}")
            continue
        if duplicates(pairs):
            failures.append(f"Duplicate provenance citation {object_id}")
        if not isinstance(grounding, dict):
            if pairs or source_grounded:
                failures.append(f"Missing grounding {object_id}")
            continue
        source_ids = grounding.get("source_ids") or []
        fragment_ids = grounding.get("fragment_ids") or []
        if duplicates(source_ids):
            failures.append(f"Duplicate grounding source ID {object_id}")
        if duplicates(fragment_ids):
            failures.append(f"Duplicate grounding fragment ID {object_id}")
        if set(source for source, _ in pairs) != set(source_ids) or set(fragment for _, fragment in pairs) != set(fragment_ids):
            failures.append(f"Provenance and grounding disagree {object_id}")
        if source_grounded and not pairs:
            failures.append(f"source_grounded without resolvable provenance {object_id}")
        for source_id, fragment_id in pairs:
            source = objects.get(str(source_id))
            if source is None or source.get("kind") != "source":
                failures.append(f"Unresolved provenance source {object_id} -> {source_id}")
                continue
            owned = {
                fragment.get("id")
                for fragment in source.get("fragments", []) or []
                if isinstance(fragment, dict)
            }
            if fragment_id not in owned:
                failures.append(
                    f"Provenance fragment belongs to wrong or missing source "
                    f"{object_id} -> {source_id}/{fragment_id}"
                )
    return failures


def validate_existing_rules(
    objects: dict[str, dict[str, Any]],
) -> list[str]:
    failures: list[str] = []
    aliases: dict[str, str] = {}

    for object_id, obj in objects.items():
        for alias in obj.get("aliases", []) or []:
            if (
                alias in aliases
                and aliases[alias] != object_id
            ):
                failures.append(
                    f"Alias conflict {alias}"
                )
            aliases[alias] = object_id

    def resolve(
        reference: str,
    ) -> str | None:
        if reference in objects:
            return reference
        return aliases.get(reference)

    def push_reference(
        found: list[str],
        value: Any,
    ) -> None:
        if (
            isinstance(value, str)
            and ID_PATTERN.match(value)
        ):
            found.append(value)

    def references(
        obj: dict[str, Any],
    ) -> list[str]:
        found: list[str] = []

        direct_keys = (
            "prerequisite_ids",
            "concept_ids",
            "competency_ids",
            "learning_objectives",
            "prerequisite_competencies",
            "recommended_question_ids",
            "misconception_ids",
            "question_ids",
            "scenario_ids",
            "learning_unit_ids",
        )

        for key in direct_keys:
            value = obj.get(key)

            if isinstance(value, list):
                for item in value:
                    push_reference(
                        found,
                        item,
                    )

        recommended = obj.get(
            "recommended_content"
        )

        if isinstance(recommended, dict):
            for value in recommended.values():
                if isinstance(value, list):
                    for item in value:
                        push_reference(
                            found,
                            item,
                        )

        for relation in (
            obj.get("relationships", []) or []
        ):
            if isinstance(relation, dict):
                push_reference(
                    found,
                    relation.get("target_id"),
                )

        for member in (
            obj.get("members", []) or []
        ):
            if isinstance(member, dict):
                push_reference(
                    found,
                    member.get("concept_id"),
                )

        for section in (
            obj.get("sections", []) or []
        ):
            if not isinstance(section, dict):
                continue

            for key in (
                "concept_ids",
                "question_ids",
                "scenario_ids",
            ):
                value = section.get(key)

                if isinstance(value, list):
                    for item in value:
                        push_reference(
                            found,
                            item,
                        )

        return found

    for object_id, obj in objects.items():
        if obj.get("status") == "published":
            for reference in references(obj):
                resolved = resolve(reference)

                if not resolved:
                    failures.append(
                        "Unresolved "
                        f"{object_id} -> {reference}"
                    )
                    continue

                target = objects[resolved]

                if (
                    target.get("status")
                    != "published"
                    and target.get("kind")
                    not in {
                        "source",
                        "generation_run",
                    }
                ):
                    failures.append(
                        "Published "
                        f"{object_id} refs "
                        f"non-published {resolved}"
                    )

            unsupported_claims = (
                obj.get("grounding") or {}
            ).get("unsupported_claims")

            if unsupported_claims:
                failures.append(
                    "Unsupported claims in published "
                    f"{object_id}"
                )

        if (
            obj.get("kind") == "concept"
            and obj.get("concept_type")
            == "contrast"
        ):
            members = obj.get("members")

            if (
                not isinstance(members, list)
                or len(members) != 2
            ):
                failures.append(
                    "Contrast "
                    f"{object_id} needs 2 members"
                )
            else:
                left = sorted(
                    (
                        members[0].get("dimensions")
                        or {}
                    ).keys()
                )
                right = sorted(
                    (
                        members[1].get("dimensions")
                        or {}
                    ).keys()
                )

                if left != right:
                    failures.append(
                        "Contrast "
                        f"{object_id} dimension "
                        f"mismatch {left} vs {right}"
                    )

    return failures

def main() -> None:
    print("Increment 0 validation - Python ADR-001..010")
    try:
        objects = load_all()
    except (OSError, UnicodeError, yaml.YAMLError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    print(f"Loaded {len(objects)} objects")
    failures = (
        validate_common(objects)
        + validate_grounding(objects)
        + validate_existing_rules(objects)
    )
    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        print("Validation failed", file=sys.stderr)
        raise SystemExit(1)
    print("All validations passed")


if __name__ == "__main__":
    main()
