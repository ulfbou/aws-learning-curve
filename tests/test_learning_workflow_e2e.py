"""End-to-end test of separate roots and one stable prepared plan."""
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
IDS = ["aws.iam.user", "aws.iam.role", "aws.iam.policy", "aws.iam.user-vs-role-vs-policy"]
ORIGINAL_HASH = "a" * 64


def concept(object_id: str, label: str, related: list[str] | None = None) -> dict:
    value = {
        "schema_version": "1.0", "id": object_id, "kind": "concept",
        "status": "candidate", "domain": "aws-cloud",
        "labels": {"en": {"preferred": label}},
        "definition": {"en": f"Fixture definition for {label}."},
        "tags": ["aws", "iam"], "aliases": [],
        "provenance": {}, "grounding": {}, "revision": 1,
        "created_at": "2026-11-01T00:00:00+00:00",
        "updated_at": "2026-11-01T00:00:00+00:00", "content_hash": ORIGINAL_HASH,
    }
    if related:
        value["concept_ids"] = related
    return value


class EndToEndTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.backend = Path(self.temp.name) / "backend-only-content"
        concepts = self.backend / "content" / "concepts"
        concepts.mkdir(parents=True)
        fixtures = {
            IDS[0]: concept(IDS[0], "IAM user"),
            IDS[1]: concept(IDS[1], "IAM role"),
            IDS[2]: concept(IDS[2], "IAM policy"),
            IDS[3]: concept(IDS[3], "IAM user versus role versus policy", IDS[:3]),
        }
        for object_id, value in fixtures.items():
            (concepts / f"{object_id}.yaml").write_text(
                yaml.safe_dump(value, allow_unicode=True, sort_keys=False), encoding="utf-8"
            )
        self.comparison_path = (
            concepts / "aws.iam.user-vs-role-vs-policy.yaml"
        )

        self.assertFalse((self.backend / "schemas").exists())
        self.assertFalse((self.backend / "scripts").exists())

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_cli(self, *args: str, expected: int = 0) -> dict:
        completed = subprocess.run(
            [sys.executable, str(CLI), "--content-workspace", str(self.backend), *args],
            cwd=ROOT, text=True, encoding="utf-8", errors="replace",
            capture_output=True, check=False,
        )
        self.assertEqual(completed.returncode, expected, msg=f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}")
        if completed.stdout.strip():
            return json.loads(completed.stdout)
        if completed.stderr.strip():
            return json.loads(completed.stderr)
        output = Path(args[args.index("-o") + 1])
        return json.loads(output.read_text(encoding="utf-8"))

    def test_complete_iam_loop(self) -> None:
        context_path = Path(self.temp.name) / "context.json"
        context = self.run_cli(
            "query", "--goal", "Understand IAM users, roles, and policies",
            "--id", IDS[3], "--kind", "concept", "--status", "candidate",
        )
        self.assertEqual([item["id"] for item in context["matches"]], [IDS[3]])
        self.assertEqual({item["id"] for item in context["related_objects"]}, set(IDS[:3]))
        self.assertTrue(all(item["path"].startswith("content/") for item in context["matches"] + context["related_objects"]))

        comparison = context["matches"][0]
        content = dict(comparison["content"])
        content["definition"] = {
            "en": (
                "An IAM user is a persistent identity, an IAM role is "
                "assumed for temporary access, and an IAM policy defines "
                "permissions."
            )
        }
        transaction = {
            "schema_version": "1.0",
            "learning_goal": "Understand IAM users, roles, and policies",
            "operations": [{
                "action": "update", "id": IDS[3], "kind": "concept",
                "expected_revision": comparison["revision"],
                "expected_content_hash": comparison["content_hash"],
                "content": content,
            }],
        }
        transaction_path = Path(self.temp.name) / "transaction.json"
        plan_path = Path(self.temp.name) / "prepared-plan.json"
        transaction_path.write_text(json.dumps(transaction), encoding="utf-8")
        plan = self.run_cli("prepare", str(transaction_path), "-o", str(plan_path))
        original = self.comparison_path.read_bytes()
        dry = self.run_cli("apply", str(plan_path))
        self.assertEqual(self.comparison_path.read_bytes(), original)
        applied = self.run_cli("apply", str(plan_path), "--execute")

        self.assertEqual(dry["prepared_at"], plan["prepared_at"])
        self.assertEqual(applied["prepared_at"], plan["prepared_at"])
        self.assertEqual(dry["plan_sha256"], applied["plan_sha256"])
        self.assertEqual(dry["planned_outputs"], applied["planned_outputs"])
        self.assertEqual(dry["planned_outputs"][0]["content_hash"], applied["planned_outputs"][0]["content_hash"])
        updated = yaml.safe_load(
            self.comparison_path.read_text(encoding="utf-8")
        )
        self.assertEqual(updated["id"], IDS[3])
        self.assertEqual(updated["concept_ids"], IDS[:3])
        self.assertEqual(updated["updated_at"], plan["prepared_at"])
        self.assertEqual(updated["content_hash"], plan["operations"][0]["content_hash"])

        stale = self.run_cli("apply", str(plan_path), "--execute", expected=1)
        self.assertIn("stale prepared plan", stale["failure"]["reason"])


if __name__ == "__main__":
    unittest.main()
