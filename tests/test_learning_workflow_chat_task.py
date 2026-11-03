"""Tests for the non-mutating chat-ready learning-task boundary."""
from __future__ import annotations
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
import yaml
ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "content_workflow.py"
GOAL = "Understand the difference between IAM users, roles, and policies."
OBJECT_ID = "aws.iam.role"
HASH = "a" * 64

def concept() -> dict:
    return {
        "schema_version": "1.0", "id": OBJECT_ID, "kind": "concept",
        "status": "candidate", "domain": "aws-cloud",
        "labels": {"en": {"preferred": "IAM role"}},
        "definition": {"en": "An IAM role can be assumed for temporary access."},
        "tags": ["iam"], "aliases": [], "provenance": {}, "grounding": {},
        "revision": 1, "created_at": "2026-11-01T00:00:00+00:00",
        "updated_at": "2026-11-01T00:00:00+00:00", "content_hash": HASH,
    }

class ChatTaskTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.backend = self.root / "backend"
        concepts = self.backend / "content" / "concepts"
        concepts.mkdir(parents=True)
        self.object_path = concepts / f"{OBJECT_ID}.yaml"
        self.object_path.write_text(yaml.safe_dump(concept(), sort_keys=False), encoding="utf-8")
        self.before = {path.relative_to(self.backend): path.read_bytes() for path in self.backend.rglob("*") if path.is_file()}
        self.task = self.root / ".dx" / "iam-learning-task.md"
        self.transaction = self.root / ".dx" / "iam-learning-transaction.json"
        self.plan = self.root / ".dx" / "iam-prepared-plan.json"
        self.dry = self.root / ".dx" / "iam-dry-run-result.json"
        self.applied = self.root / ".dx" / "iam-apply-result.json"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_task(self, expected: int = 0) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run([
            sys.executable, str(CLI), "--content-workspace", str(self.backend),
            "chat-task", "--goal", GOAL, "--tag", "iam", "--kind", "concept",
            "--status", "candidate", "-o", str(self.task),
            "--transaction-output", str(self.transaction),
            "--prepared-plan-output", str(self.plan),
            "--dry-run-output", str(self.dry), "--apply-output", str(self.applied),
        ], cwd=ROOT, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False)
        self.assertEqual(completed.returncode, expected, msg=f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}")
        return completed

    def test_chat_task_is_complete_bounded_and_non_mutating(self) -> None:
        completed = self.run_task()
        text = self.task.read_text(encoding="utf-8")
        self.assertIn(GOAL, text)
        self.assertIn(OBJECT_ID, text)
        self.assertIn('"title": "Bounded learning artifact transaction"', text)
        self.assertIn("Return exactly one JSON object", text)
        self.assertIn("semantic learning content only", text)
        for field in ("path", "revision", "created_at", "updated_at", "content_hash", "prepared_at", "plan_sha256", "payload_sha256"):
            self.assertIn(f"`{field}`", text)
        self.assertIn(self.transaction.as_posix(), text)
        self.assertIn(self.plan.as_posix(), text)
        self.assertIn("Execution is a distinct human-reviewed command", text)
        self.assertIn("INFO expected AI transaction", completed.stdout)
        after = {path.relative_to(self.backend): path.read_bytes() for path in self.backend.rglob("*") if path.is_file()}
        self.assertEqual(after, self.before)
        self.assertFalse((self.root / ".authoring").exists())
        self.assertFalse((self.root / ".private").exists())

    def test_documented_transaction_shape_prepares_with_existing_engine(self) -> None:
        self.run_task()
        current = concept()
        content = dict(current)
        content["definition"] = {"en": "A role is assumed and supplies temporary permissions."}
        for field in ("id", "kind", "revision", "created_at", "updated_at", "content_hash"):
            content.pop(field, None)
        transaction = {
            "schema_version": "1.0", "learning_goal": GOAL,
            "operations": [{
                "action": "update", "id": OBJECT_ID, "kind": "concept",
                "expected_revision": 1, "expected_content_hash": HASH, "content": content,
            }],
        }
        self.transaction.write_text(json.dumps(transaction), encoding="utf-8")
        completed = subprocess.run([
            sys.executable, str(CLI), "--content-workspace", str(self.backend),
            "prepare", str(self.transaction), "-o", str(self.plan),
        ], cwd=ROOT, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False)
        self.assertEqual(completed.returncode, 0, msg=completed.stdout + completed.stderr)
        prepared = json.loads(self.plan.read_text(encoding="utf-8"))
        self.assertEqual(prepared["plan_type"], "prepared_learning_transaction")
        self.assertEqual(prepared["changes"]["updated"], [OBJECT_ID])

    def test_invalid_ai_output_reports_prepare_phase_and_reason(self) -> None:
        self.transaction.parent.mkdir(parents=True, exist_ok=True)
        self.transaction.write_text('{"schema_version":"1.0"}', encoding="utf-8")
        completed = subprocess.run([
            sys.executable, str(CLI), "--content-workspace", str(self.backend),
            "prepare", str(self.transaction), "-o", str(self.plan),
        ], cwd=ROOT, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False)
        self.assertEqual(completed.returncode, 1)
        failure = json.loads(self.plan.read_text(encoding="utf-8"))
        self.assertEqual(failure["failure"]["phase"], "prepare")
        self.assertIn("invalid transaction", failure["failure"]["reason"])

if __name__ == "__main__":
    unittest.main()
