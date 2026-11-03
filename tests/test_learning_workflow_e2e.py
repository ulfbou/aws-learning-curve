"""End-to-end test for the bounded learning workflow CLI."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "content_workflow.py"
TRANSACTION_SCHEMA = ROOT / "schemas" / "learning-transaction.schema.json"
OBJECT_ID = "aws.iam.role"
ORIGINAL_HASH = "a" * 64


def initial_object() -> dict:
    return {
        "schema_version": "1.0",
        "id": OBJECT_ID,
        "kind": "concept",
        "status": "candidate",
        "domain": "aws-cloud",
        "labels": {"en": {"preferred": "IAM role"}},
        "definition": {"en": "An existing learning definition."},
        "key_points": ["A role is assumed."],
        "tags": ["aws", "iam"],
        "provenance": {
            "sources": [],
            "transformation": {
                "method": "human_authored",
                "run_id": "test.e2e.initial",
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
        "revision": 1,
        "created_at": "2026-11-01T00:00:00+00:00",
        "updated_at": "2026-11-01T00:00:00+00:00",
        "content_hash": ORIGINAL_HASH,
        "aliases": [],
    }


class BoundedLearningWorkflowEndToEndTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name)

        (self.workspace / "content" / "concepts").mkdir(parents=True)
        (self.workspace / "schemas").mkdir()
        (self.workspace / "scripts" / "learning_workflow").mkdir(
            parents=True
        )

        shutil.copy2(CLI, self.workspace / "scripts" / CLI.name)
        shutil.copy2(
            ROOT / "scripts" / "learning_workflow" / "__init__.py",
            self.workspace / "scripts" / "learning_workflow" / "__init__.py",
        )
        shutil.copy2(
            ROOT / "scripts" / "learning_workflow" / "engine.py",
            self.workspace / "scripts" / "learning_workflow" / "engine.py",
        )
        shutil.copy2(
            TRANSACTION_SCHEMA,
            self.workspace / "schemas" / TRANSACTION_SCHEMA.name,
        )

        self.object_path = (
            self.workspace
            / "content"
            / "concepts"
            / f"{OBJECT_ID}.yaml"
        )
        self.object_path.write_text(
            yaml.safe_dump(
                initial_object(),
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )

        # The workflow must invoke a repository-owned validator in both
        # dry-run and execute mode. This fixture validator checks the
        # fields whose ownership the workflow is expected to enforce.
        (self.workspace / "scripts" / "validate_content.py").write_text(
            """
from pathlib import Path
import re
import yaml

root = Path(__file__).resolve().parents[1]
path = root / "content" / "concepts" / "aws.iam.role.yaml"
obj = yaml.safe_load(path.read_text(encoding="utf-8"))
assert obj["id"] == "aws.iam.role"
assert obj["kind"] == "concept"
assert isinstance(obj["revision"], int) and obj["revision"] >= 1
assert re.fullmatch(r"[a-f0-9]{64}", obj["content_hash"])
print("fixture repository validation passed")
""".lstrip(),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_cli(
        self,
        *arguments: str,
        expected: int = 0,
    ) -> dict:
        completed = subprocess.run(
            [
                sys.executable,
                str(
                    self.workspace
                    / "scripts"
                    / "content_workflow.py"
                ),
                "--workspace",
                str(self.workspace),
                *arguments,
            ],
            cwd=self.workspace,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            completed.returncode,
            expected,
            msg=(
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            ),
        )
        return json.loads(completed.stdout)

    def write_transaction(
        self,
        context: dict,
    ) -> Path:
        match = context["matches"][0]
        content = dict(match["content"])
        content["definition"] = {
            "en": (
                "An IAM identity with temporary permissions that is "
                "assumed by a trusted principal."
            )
        }

        # AI-supplied system fields must not control the resulting object.
        content["revision"] = 999
        content["created_at"] = "1900-01-01T00:00:00+00:00"
        content["updated_at"] = "1900-01-01T00:00:00+00:00"
        content["content_hash"] = "f" * 64

        transaction = {
            "schema_version": "1.0",
            "learning_goal": "Understand IAM roles.",
            "operations": [
                {
                    "action": "update",
                    "id": OBJECT_ID,
                    "kind": "concept",
                    "expected_revision": match["revision"],
                    "expected_content_hash": match["content_hash"],
                    "content": content,
                }
            ],
        }

        path = self.workspace / "transaction.json"
        path.write_text(
            json.dumps(
                transaction,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return path

    def test_query_prepare_dry_run_apply_and_stale_conflict(
        self,
    ) -> None:
        context = self.run_cli(
            "query",
            "--goal",
            "Understand IAM roles.",
            "--id",
            OBJECT_ID,
            "--kind",
            "concept",
            "--status",
            "candidate",
        )

        self.assertEqual(
            context["packet_type"],
            "learning_context",
        )
        self.assertEqual(
            [item["id"] for item in context["matches"]],
            [OBJECT_ID],
        )
        self.assertEqual(
            context["matches"][0]["revision"],
            1,
        )
        self.assertEqual(
            context["matches"][0]["content_hash"],
            ORIGINAL_HASH,
        )

        transaction = self.write_transaction(context)

        prepared = self.run_cli(
            "prepare",
            str(transaction),
        )
        self.assertEqual(
            prepared["operation"],
            "prepare",
        )
        self.assertEqual(
            prepared["result"],
            "success",
        )
        self.assertEqual(
            prepared["changes"]["updated"],
            [OBJECT_ID],
        )

        before_dry_run = self.object_path.read_bytes()

        dry_run = self.run_cli(
            "apply",
            str(transaction),
        )
        self.assertEqual(
            dry_run["operation"],
            "dry_run",
        )
        self.assertEqual(
            dry_run["result"],
            "success",
        )
        self.assertEqual(
            self.object_path.read_bytes(),
            before_dry_run,
        )

        applied = self.run_cli(
            "apply",
            str(transaction),
            "--execute",
        )
        self.assertEqual(
            applied["operation"],
            "apply",
        )
        self.assertEqual(
            applied["result"],
            "success",
        )
        self.assertEqual(
            applied["changes"]["updated"],
            [OBJECT_ID],
        )

        updated = yaml.safe_load(
            self.object_path.read_text(encoding="utf-8")
        )
        self.assertEqual(
            updated["revision"],
            2,
        )
        self.assertEqual(
            updated["created_at"],
            "2026-11-01T00:00:00+00:00",
        )
        self.assertNotEqual(
            updated["updated_at"],
            "1900-01-01T00:00:00+00:00",
        )
        self.assertNotEqual(
            updated["content_hash"],
            "f" * 64,
        )
        self.assertEqual(
            updated["definition"]["en"],
            (
                "An IAM identity with temporary permissions that is "
                "assumed by a trusted principal."
            ),
        )

        # Reusing the accepted transaction must fail because its expected
        # revision and hash describe the pre-apply repository state.
        stale = self.run_cli(
            "apply",
            str(transaction),
            "--execute",
            expected=1,
        )
        self.assertEqual(
            stale["result"],
            "failure",
        )
        self.assertEqual(
            stale["failure"]["category"],
            "workflow_error",
        )
        self.assertIn(
            "revision conflict",
            stale["failure"]["reason"],
        )

        after_conflict = yaml.safe_load(
            self.object_path.read_text(encoding="utf-8")
        )
        self.assertEqual(
            after_conflict,
            updated,
        )


if __name__ == "__main__":
    unittest.main()
