"""Regression tests for the public-content release boundary."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
BUILDER = (
    ROOT
    / "scripts"
    / "build_learning_bundle.py"
)
VERIFIER = (
    ROOT
    / "scripts"
    / "verify_pages.py"
)

SOURCE_ID = "source.private.release-sentinel"
FRAGMENT_ID = "fragment.private.release-sentinel"
CONCEPT_ID = "aws.iam.public-sentinel"

SENTINELS = {
    "SOURCE_EXACT_TEXT_SENTINEL_7F3A",
    "SOURCE_NORMALIZED_TEXT_SENTINEL_9C21",
    "SOURCE_LOCAL_PATH_SENTINEL_4D88",
    "SOURCE_LOCATOR_SENTINEL_2A65",
    ".dx/private-release-sentinel.txt",
    ".private/learner-release-sentinel.json",
    ".authoring/source-release-sentinel.json",
}


def load_verifier_module():
    specification = (
        importlib.util.spec_from_file_location(
            "test_verify_pages",
            VERIFIER,
        )
    )

    if (
        specification is None
        or specification.loader is None
    ):
        raise RuntimeError(
            "could not load verify_pages.py"
        )

    module = (
        importlib.util.module_from_spec(
            specification
        )
    )
    specification.loader.exec_module(module)
    return module


def source_fixture() -> dict:
    return {
        "schema_version": "1.0",
        "id": SOURCE_ID,
        "kind": "source",
        "status": "published",
        "title": (
            "Internal registered source"
        ),
        "source_type": "own_notes",
        "language": "sv-SE",
        "origin": {
            "path": (
                "F:/private/"
                "SOURCE_LOCAL_PATH_SENTINEL_4D88/"
                "notes.md"
            ),
            "external_url": None,
            "captured_at": (
                "2026-11-03T00:00:00+00:00"
            ),
            "content_hash": "a" * 64,
        },
        "fragments": [
            {
                "id": FRAGMENT_ID,
                "heading": (
                    "SOURCE_LOCATOR_SENTINEL_2A65"
                ),
                "language": "sv-SE",
                "content_fingerprint": (
                    "b" * 16
                ),
                "locator": {
                    "section": (
                        ".dx/"
                        "private-release-sentinel.txt"
                    ),
                    "page": 7,
                    "start_offset": 11,
                    "end_offset": 29,
                },
                "exact_text": (
                    "SOURCE_EXACT_TEXT_SENTINEL_7F3A "
                    ".private/"
                    "learner-release-sentinel.json"
                ),
                "normalized_text": (
                    "SOURCE_NORMALIZED_TEXT_SENTINEL_9C21 "
                    ".authoring/"
                    "source-release-sentinel.json"
                ),
                "noise_removed": [],
            },
        ],
        "relationships": [],
        "revision": 1,
        "created_at": (
            "2026-11-03T00:00:00+00:00"
        ),
        "updated_at": (
            "2026-11-03T00:00:00+00:00"
        ),
        "content_hash": "c" * 64,
        "aliases": [
            "source.private.alias"
        ],
    }


def concept_fixture() -> dict:
    return {
        "schema_version": "1.0",
        "id": CONCEPT_ID,
        "kind": "concept",
        "concept_type": "entity",
        "status": "published",
        "domain": "aws-cloud",
        "labels": {
            "sv-SE": {
                "preferred": (
                    "Offentligt IAM-begrepp"
                ),
            },
        },
        "definition": {
            "sv-SE": (
                "Ett publicerbart lärbegrepp "
                "som behåller källreferenser."
            ),
        },
        "tags": [
            "iam",
            "public-boundary",
        ],
        "relationships": [],
        "aliases": [
            "aws.iam.public-alias"
        ],
        "provenance": {
            "sources": [
                {
                    "source_id": SOURCE_ID,
                    "fragment_id": FRAGMENT_ID,
                    "relation": (
                        "directly_supports"
                    ),
                },
            ],
            "transformation": {
                "method": "human_authored",
                "run_id": "run.public.sentinel",
                "fidelity": "paraphrase",
            },
            "verification": {
                "source_grounded": True,
                "externally_verified": False,
                "verified_at": None,
            },
            "unsupported_fields": [],
        },
        "grounding": {
            "source_ids": [
                SOURCE_ID,
            ],
            "fragment_ids": [
                FRAGMENT_ID,
            ],
            "concept_ids": [],
            "unsupported_claims": [],
        },
        "revision": 1,
        "created_at": (
            "2026-11-03T00:00:00+00:00"
        ),
        "updated_at": (
            "2026-11-03T00:00:00+00:00"
        ),
        "content_hash": "d" * 64,
    }


class PublicContentBoundaryTests(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.temporary = (
            tempfile.TemporaryDirectory()
        )
        self.workspace = Path(
            self.temporary.name
        )

        scripts = self.workspace / "scripts"
        scripts.mkdir(parents=True)

        shutil.copy2(
            BUILDER,
            scripts / BUILDER.name,
        )

        (
            self.workspace
            / "content"
            / "sources"
            / "fixtures"
        ).mkdir(parents=True)

        (
            self.workspace
            / "content"
            / "concepts"
            / "fixtures"
        ).mkdir(parents=True)

        (
            self.workspace
            / "content"
            / "sources"
            / "fixtures"
            / "source.yaml"
        ).write_text(
            yaml.safe_dump(
                source_fixture(),
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )

        (
            self.workspace
            / "content"
            / "concepts"
            / "fixtures"
            / "concept.yaml"
        ).write_text(
            yaml.safe_dump(
                concept_fixture(),
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )

        (
            self.workspace
            / "content"
            / "manifest.yaml"
        ).write_text(
            yaml.safe_dump(
                {
                    "content_version": (
                        "2026-11-03.6"
                    ),
                    "generated_at": (
                        "2026-11-03T00:00:00+00:00"
                    ),
                    "aliases": {
                        "source.manifest.alias": (
                            SOURCE_ID
                        ),
                        "concept.manifest.alias": (
                            CONCEPT_ID
                        ),
                    },
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_builder(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                str(
                    self.workspace
                    / "scripts"
                    / BUILDER.name
                ),
            ],
            cwd=self.workspace,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(
            completed.returncode,
            0,
            msg=(
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            ),
        )

    def test_registered_source_is_not_public(
        self,
    ) -> None:
        self.run_builder()

        data = (
            self.workspace
            / "public"
            / "data"
        )
        bundle_path = (
            data
            / "learning-bundle.json"
        )
        manifest_path = (
            data
            / "learning-bundle.manifest.json"
        )

        bundle_text = bundle_path.read_text(
            encoding="utf-8"
        )
        manifest_text = (
            manifest_path.read_text(
                encoding="utf-8"
            )
        )
        release_json = (
            bundle_text
            + "\n"
            + manifest_text
        )

        bundle = json.loads(bundle_text)
        manifest = json.loads(
            manifest_text
        )

        self.assertEqual(
            bundle["sources"],
            {},
        )
        self.assertEqual(
            bundle["manifest"]["counts"]["sources"],
            0,
        )
        self.assertTrue(
            bundle["manifest"][
                "registeredSourcesExcluded"
            ]
        )

        self.assertIn(
            CONCEPT_ID,
            bundle["concepts"],
        )
        self.assertEqual(
            bundle["concepts"][CONCEPT_ID]
            ["grounding"]["source_ids"],
            [SOURCE_ID],
        )
        self.assertEqual(
            bundle["concepts"][CONCEPT_ID]
            ["grounding"]["fragment_ids"],
            [FRAGMENT_ID],
        )

        self.assertEqual(
            set(
                manifest[
                    "perObjectHashes"
                ]
            ),
            {CONCEPT_ID},
        )

        self.assertNotIn(
            "source.private.alias",
            bundle["aliasMap"],
        )
        self.assertNotIn(
            "source.manifest.alias",
            bundle["aliasMap"],
        )
        self.assertEqual(
            bundle["aliasMap"][
                "concept.manifest.alias"
            ],
            CONCEPT_ID,
        )

        for sentinel in SENTINELS:
            self.assertNotIn(
                sentinel,
                release_json,
            )

        verifier = load_verifier_module()
        violations = []

        for path in sorted(
            data.rglob("*.json")
        ):
            violations.extend(
                verifier
                .collect_public_boundary_violations(
                    json.loads(
                        path.read_text(
                            encoding="utf-8"
                        )
                    ),
                    location=path.name,
                )
            )

        self.assertEqual(
            violations,
            [],
        )

    def test_public_validator_rejects_source_fields(
        self,
    ) -> None:
        verifier = load_verifier_module()

        violations = (
            verifier
            .collect_public_boundary_violations(
                {
                    "origin": {
                        "path": (
                            "F:/private/source.md"
                        ),
                    },
                    "exact_text": (
                        "SOURCE_EXACT_TEXT_"
                        "SENTINEL_7F3A"
                    ),
                    "locator": {
                        "section": (
                            ".dx/private.txt"
                        ),
                    },
                },
                location="fixture.json",
            )
        )

        self.assertTrue(
            any(
                "origin.path" in value
                for value in violations
            )
        )
        self.assertTrue(
            any(
                "exact_text" in value
                for value in violations
            )
        )
        self.assertTrue(
            any(
                "locator" in value
                for value in violations
            )
        )
        self.assertTrue(
            any(
                ".dx/" in value
                for value in violations
            )
        )


if __name__ == "__main__":
    unittest.main()
