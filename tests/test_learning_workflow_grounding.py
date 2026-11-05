"""Focused tests for canonical source grounding during preparation."""
from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from learning_workflow.engine import (  # noqa: E402
    WorkflowError,
    build_source_record,
    prepare_transaction,
)

SOURCE_A = "source.aws.vpc.a"
SOURCE_B = "source.aws.vpc.b"
FRAGMENT_A = f"{SOURCE_A}.fragment.001"
FRAGMENT_B = f"{SOURCE_B}.fragment.001"


class GroundingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.backend = self.root / "backend"
        sources = self.backend / "content" / "sources"
        sources.mkdir(parents=True)

        for source_id, text in (
            (SOURCE_A, "VPC boundary."),
            (SOURCE_B, "Route table."),
        ):
            path = self.root / f"{source_id}.txt"
            path.write_text(text, encoding="utf-8")
            record = build_source_record(
                path,
                source_id,
                source_id,
                "course_notes",
                "en-US",
                "2026-01-01T00:00:00+00:00",
            )
            (sources / f"{source_id}.yaml").write_text(
                yaml.safe_dump(
                    record,
                    allow_unicode=True,
                    sort_keys=False,
                ),
                encoding="utf-8",
            )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def transaction(self) -> dict:
        return {
            "schema_version": "1.0",
            "learning_goal": "Understand a VPC boundary.",
            "operations": [
                {
                    "action": "create",
                    "id": "aws.vpc.boundary",
                    "kind": "concept",
                    "content": {
                        "schema_version": "1.0",
                        "status": "candidate",
                        "domain": "aws-cloud",
                        "concept_type": "entity",
                        "labels": {
                            "en-US": {
                                "preferred": "VPC",
                            }
                        },
                        "definition": {
                            "en-US": (
                                "A regional network boundary."
                            )
                        },
                        "provenance": {
                            "sources": [
                                {
                                    "source_id": SOURCE_A,
                                    "fragment_id": FRAGMENT_A,
                                    "relation": (
                                        "directly_supports"
                                    ),
                                }
                            ],
                            "transformation": {
                                "method": "llm_extraction",
                                "fidelity": "paraphrase",
                                "run_id": "ignored",
                            },
                            "verification": {
                                "source_grounded": True,
                                "externally_verified": False,
                                "verified_at": None,
                            },
                            "unsupported_fields": [],
                        },
                        "grounding": {
                            "source_ids": [SOURCE_A],
                            "fragment_ids": [FRAGMENT_A],
                            "unsupported_claims": [],
                        },
                        "aliases": [],
                        "tags": ["vpc"],
                    },
                }
            ],
        }

    def reject(
        self,
        transaction: dict,
        message: str,
    ) -> None:
        with self.assertRaisesRegex(
            WorkflowError,
            message,
        ):
            prepare_transaction(
                ROOT,
                self.backend,
                transaction,
                prepared_at=(
                    "2026-01-01T00:00:00+00:00"
                ),
            )

    def test_accepts_exact_registered_grounding(
        self,
    ) -> None:
        plan = prepare_transaction(
            ROOT,
            self.backend,
            self.transaction(),
            prepared_at="2026-01-01T00:00:00+00:00",
        )
        self.assertEqual(len(plan["operations"]), 2)

    def test_rejects_missing_source_missing_fragment_wrong_owner_and_disagreement(
        self,
    ) -> None:
        transaction = self.transaction()
        citation = (
            transaction["operations"][0]["content"]
            ["provenance"]["sources"][0]
        )
        citation["source_id"] = "source.aws.missing"
        (
            transaction["operations"][0]["content"]
            ["grounding"]["source_ids"]
        ) = ["source.aws.missing"]
        self.reject(transaction, "not registered")

        transaction = self.transaction()
        (
            transaction["operations"][0]["content"]
            ["provenance"]["sources"][0]["fragment_id"]
        ) = "fragment.missing.001"
        (
            transaction["operations"][0]["content"]
            ["grounding"]["fragment_ids"]
        ) = ["fragment.missing.001"]
        self.reject(
            transaction,
            "fragment is not registered",
        )

        transaction = self.transaction()
        (
            transaction["operations"][0]["content"]
            ["provenance"]["sources"][0]["fragment_id"]
        ) = FRAGMENT_B
        (
            transaction["operations"][0]["content"]
            ["grounding"]["fragment_ids"]
        ) = [FRAGMENT_B]
        self.reject(
            transaction,
            (
                "fragment is not registered for "
                "source.aws.vpc.a"
            ),
        )

        transaction = self.transaction()
        (
            transaction["operations"][0]["content"]
            ["grounding"]["fragment_ids"]
        ) = []
        self.reject(
            transaction,
            "references disagree",
        )

    def test_rejects_duplicates_source_grounded_without_citations_and_modified_fingerprint(
        self,
    ) -> None:
        transaction = self.transaction()
        content = (
            transaction["operations"][0]["content"]
        )
        content["provenance"]["sources"].append(
            copy.deepcopy(
                content["provenance"]["sources"][0]
            )
        )
        self.reject(
            transaction,
            "duplicate source citations",
        )

        transaction = self.transaction()
        (
            transaction["operations"][0]["content"]
            ["grounding"]["source_ids"]
        ).append(SOURCE_A)
        self.reject(
            transaction,
            "duplicate source IDs",
        )

        transaction = self.transaction()
        (
            transaction["operations"][0]["content"]
            ["provenance"]["sources"]
        ) = []
        (
            transaction["operations"][0]["content"]
            ["grounding"]
        ) = {
            "source_ids": [],
            "fragment_ids": [],
            "unsupported_claims": [],
        }
        self.reject(
            transaction,
            (
                "source_grounded requires "
                "resolvable provenance"
            ),
        )

        source_path = (
            self.backend
            / "content"
            / "sources"
            / f"{SOURCE_A}.yaml"
        )
        source = yaml.safe_load(
            source_path.read_text(encoding="utf-8")
        )
        source["fragments"][0][
            "content_fingerprint"
        ] = "0" * 32
        source_path.write_text(
            yaml.safe_dump(
                source,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        self.reject(
            self.transaction(),
            "fingerprint mismatch",
        )


if __name__ == "__main__":
    unittest.main()
