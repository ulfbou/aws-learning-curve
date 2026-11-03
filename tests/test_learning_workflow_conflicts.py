"""Conflict-handling tests for the bounded learning workflow."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from learning_workflow.engine import (  # noqa: E402
    WorkflowError,
    apply_transaction,
    plan_transaction,
    planned_writes,
    prepare_transaction,
)


OBJECT_ID = "aws.iam.role"
ORIGINAL_HASH = "a" * 64


def transaction_schema() -> dict:
    return json.loads(
        (ROOT / "schemas" / "learning-transaction.schema.json").read_text(
            encoding="utf-8"
        )
    )


def existing_object() -> dict:
    return {
        "schema_version": "1.0",
        "id": OBJECT_ID,
        "kind": "concept",
        "status": "candidate",
        "domain": "aws-cloud",
        "labels": {"en": {"preferred": "IAM role"}},
        "definition": {"en": "Existing definition."},
        "provenance": {
            "sources": [],
            "transformation": {
                "method": "human_authored",
                "run_id": "test.run",
                "fidelity": "generated",
            },
            "verification": {
                "source_grounded": False,
                "externally_verified": False,
                "verified_at": None,
            },
            "unsupported_fields": [],
        },
        "grounding": {
            "source_ids": [],
            "fragment_ids": [],
            "unsupported_claims": [],
        },
        "revision": 3,
        "created_at": "2026-11-01T00:00:00+00:00",
        "updated_at": "2026-11-01T00:00:00+00:00",
        "content_hash": ORIGINAL_HASH,
        "aliases": [],
    }


def proposed_content() -> dict:
    obj = existing_object()
    obj["definition"] = {"en": "Improved definition."}
    for key in (
        "id",
        "kind",
        "revision",
        "created_at",
        "updated_at",
        "content_hash",
    ):
        obj.pop(key, None)
    return obj


def update_transaction(**overrides) -> dict:
    operation = {
        "action": "update",
        "id": OBJECT_ID,
        "kind": "concept",
        "expected_revision": 3,
        "expected_content_hash": ORIGINAL_HASH,
        "content": proposed_content(),
    }
    operation.update(overrides)
    return {
        "schema_version": "1.0",
        "learning_goal": "Understand IAM roles.",
        "operations": [operation],
    }


class ConflictHandlingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

        (self.root / "content" / "concepts").mkdir(parents=True)
        (self.root / "schemas").mkdir()

        (
            self.root
            / "schemas"
            / "learning-transaction.schema.json"
        ).write_text(
            json.dumps(transaction_schema()),
            encoding="utf-8",
        )

        self.object_path = (
            self.root
            / "content"
            / "concepts"
            / f"{OBJECT_ID}.yaml"
        )
        self.object_path.write_text(
            yaml.safe_dump(
                existing_object(),
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        self.original_bytes = self.object_path.read_bytes()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def assert_conflict(
        self,
        transaction: dict,
        message: str,
    ) -> None:
        with self.assertRaisesRegex(WorkflowError, message):
            plan_transaction(self.root, transaction)

        self.assertEqual(
            self.object_path.read_bytes(),
            self.original_bytes,
        )

    def test_rejects_stale_revision(self) -> None:
        self.assert_conflict(
            update_transaction(expected_revision=2),
            r"revision conflict for aws\.iam\.role",
        )

    def test_rejects_stale_content_hash(self) -> None:
        self.assert_conflict(
            update_transaction(
                expected_content_hash="b" * 64
            ),
            r"content hash conflict for aws\.iam\.role",
        )

    def test_rejects_create_when_target_exists(self) -> None:
        transaction = update_transaction(action="create")
        operation = transaction["operations"][0]
        operation.pop("expected_revision")
        operation.pop("expected_content_hash")

        self.assert_conflict(
            transaction,
            r"create target already exists: aws\.iam\.role",
        )

    def test_rejects_update_when_target_is_missing(self) -> None:
        self.object_path.unlink()

        with self.assertRaisesRegex(
            WorkflowError,
            r"update target does not exist: aws\.iam\.role",
        ):
            plan_transaction(
                self.root,
                update_transaction(),
            )

        self.assertFalse(self.object_path.exists())

    def test_rejects_kind_change(self) -> None:
        self.assert_conflict(
            update_transaction(kind="question"),
            r"kind cannot change for aws\.iam\.role",
        )

    def test_rejects_duplicate_operations(self) -> None:
        transaction = update_transaction()
        transaction["operations"].append(
            dict(transaction["operations"][0])
        )

        self.assert_conflict(
            transaction,
            r"duplicate operation for aws\.iam\.role",
        )

    def test_apply_rolls_back_when_repository_validation_fails(
        self,
    ) -> None:
        with patch(
            "learning_workflow.engine.run_repository_validator",
            side_effect=WorkflowError(
                "simulated validation failure"
            ),
        ):
            with self.assertRaisesRegex(
                WorkflowError,
                "simulated validation failure",
            ):
                apply_transaction(
                    self.root,
                    update_transaction(),
                )

        self.assertEqual(
            self.object_path.read_bytes(),
            self.original_bytes,
        )
        generation_runs = self.root / "content" / "generation-runs"
        self.assertEqual(
            list(generation_runs.glob("*.yaml"))
            if generation_runs.exists()
            else [],
            [],
        )

    def test_successful_plan_does_not_mutate_repository(
        self,
    ) -> None:
        result, writes = plan_transaction(
            self.root,
            update_transaction(),
        )

        self.assertEqual(
            result["changes"]["updated"],
            [OBJECT_ID],
        )
        self.assertEqual(len(writes), 2)
        self.assertEqual(
            result["generation_run_id"],
            writes[1][0].stem,
        )
        self.assertEqual(
            self.object_path.read_bytes(),
            self.original_bytes,
        )

    def test_semantically_identical_plans_have_same_content_hash(
        self,
    ) -> None:
        first = prepare_transaction(
            self.root,
            self.root,
            update_transaction(),
            prepared_at="2026-11-03T08:00:00+00:00",
        )
        second = prepare_transaction(
            self.root,
            self.root,
            update_transaction(),
            prepared_at="2026-11-03T09:00:00+00:00",
        )

        first_operation = first["operations"][0]
        second_operation = second["operations"][0]

        self.assertEqual(
            first_operation["content_hash"],
            second_operation["content_hash"],
        )
        self.assertNotEqual(
            first_operation["payload_sha256"],
            second_operation["payload_sha256"],
        )
        self.assertNotEqual(
            first["plan_sha256"],
            second["plan_sha256"],
        )


    def test_python_owns_matching_generation_run_metadata(self) -> None:
        candidate = update_transaction()
        candidate["operations"][0]["content"]["provenance"][
            "transformation"
        ]["run_id"] = "generation.ai-selected"

        first = prepare_transaction(
            self.root,
            self.root,
            candidate,
            prepared_at="2026-11-03T08:00:00+00:00",
        )
        second = prepare_transaction(
            self.root,
            self.root,
            update_transaction(),
            prepared_at="2026-11-03T09:00:00+00:00",
        )

        self.assertEqual(
            first["generation_run_id"],
            second["generation_run_id"],
        )
        self.assertNotEqual(
            first["generation_run_id"],
            "generation.ai-selected",
        )

        object_payload = yaml.safe_load(
            __import__("base64").b64decode(
                first["operations"][0]["payload_base64"]
            ).decode("utf-8")
        )
        run_payload = yaml.safe_load(
            __import__("base64").b64decode(
                first["operations"][1]["payload_base64"]
            ).decode("utf-8")
        )

        self.assertEqual(
            object_payload["provenance"]["transformation"]["run_id"],
            first["generation_run_id"],
        )
        self.assertEqual(run_payload["id"], first["generation_run_id"])
        self.assertEqual(run_payload["outputs"], first["changes"])
        self.assertEqual(first["changes"]["updated"], [OBJECT_ID])
        self.assertEqual(first["changes"]["created"], [])
        self.assertEqual(first["changes"]["unchanged"], [])

    def test_generation_run_target_participates_in_stale_check(self) -> None:
        plan = prepare_transaction(
            self.root,
            self.root,
            update_transaction(),
            prepared_at="2026-11-03T08:00:00+00:00",
        )
        run_path = (
            self.root
            / "content"
            / "generation-runs"
            / f"{plan['generation_run_id']}.yaml"
        )
        run_path.parent.mkdir(parents=True)
        run_path.write_text("unexpected", encoding="utf-8")

        with self.assertRaisesRegex(
            WorkflowError,
            "stale prepared plan for generation",
        ):
            planned_writes(self.root, plan)


if __name__ == "__main__":
    unittest.main()
