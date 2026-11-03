"""Tests for the non-mutating, pipe-friendly chat-task boundary."""

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

GOAL = (
    "Understand the difference between IAM users, "
    "roles, and policies."
)
OBJECT_ID = "aws.iam.role"
HASH = "a" * 64


def concept() -> dict:
    return {
        "schema_version": "1.0",
        "id": OBJECT_ID,
        "kind": "concept",
        "status": "candidate",
        "domain": "aws-cloud",
        "labels": {
            "en": {
                "preferred": "IAM role",
            },
        },
        "definition": {
            "en": (
                "An IAM role can be assumed "
                "for temporary access."
            ),
        },
        "tags": ["iam"],
        "aliases": [],
        "provenance": {},
        "grounding": {},
        "revision": 1,
        "created_at": "2026-11-01T00:00:00+00:00",
        "updated_at": "2026-11-01T00:00:00+00:00",
        "content_hash": HASH,
    }


def transaction() -> dict:
    content = dict(concept())
    content["definition"] = {
        "en": (
            "A role is assumed and supplies "
            "temporary permissions."
        ),
    }

    for field in (
        "id",
        "kind",
        "revision",
        "created_at",
        "updated_at",
        "content_hash",
    ):
        content.pop(field, None)

    return {
        "schema_version": "1.0",
        "learning_goal": GOAL,
        "operations": [
            {
                "action": "update",
                "id": OBJECT_ID,
                "kind": "concept",
                "expected_revision": 1,
                "expected_content_hash": HASH,
                "content": content,
            },
        ],
    }


class ChatTaskTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.backend = self.root / "backend"

        concepts = (
            self.backend
            / "content"
            / "concepts"
        )
        concepts.mkdir(parents=True)

        (
            concepts
            / f"{OBJECT_ID}.yaml"
        ).write_text(
            yaml.safe_dump(
                concept(),
                sort_keys=False,
            ),
            encoding="utf-8",
        )

        self.before = {
            path.relative_to(self.backend):
                path.read_bytes()
            for path in self.backend.rglob("*")
            if path.is_file()
        }

        self.task = (
            self.root
            / ".dx"
            / "iam-learning-task.md"
        )
        self.plan = (
            self.root
            / ".dx"
            / "iam-prepared-plan.json"
        )
        self.dry = (
            self.root
            / ".dx"
            / "iam-dry-run-result.json"
        )
        self.applied = (
            self.root
            / ".dx"
            / "iam-apply-result.json"
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def command(
        self,
        *parts: str,
    ) -> list[str]:
        return [
            sys.executable,
            str(CLI),
            "--content-workspace",
            str(self.backend),
            *parts,
        ]

    def repository_files(self) -> dict[Path, bytes]:
        return {
            path.relative_to(self.backend):
                path.read_bytes()
            for path in self.backend.rglob("*")
            if path.is_file()
        }

    def run_task(
        self,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            self.command(
                "chat-task",
                "--goal",
                GOAL,
                "--tag",
                "iam",
                "--kind",
                "concept",
                "--status",
                "candidate",
                "-o",
                str(self.task),
                "--prepared-plan-output",
                str(self.plan),
                "--dry-run-output",
                str(self.dry),
                "--apply-output",
                str(self.applied),
            ),
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

    def test_chat_task_emits_pipe_friendly_command_and_is_non_mutating(
        self,
    ) -> None:
        completed = self.run_task()

        self.assertEqual(
            completed.returncode,
            0,
            msg=completed.stderr,
        )
        self.assertEqual(
            completed.stdout,
            "",
        )
        self.assertIn(
            "INFO chat task:",
            completed.stderr,
        )

        text = self.task.read_text(
            encoding="utf-8",
        )

        self.assertIn(GOAL, text)
        self.assertIn(OBJECT_ID, text)
        self.assertIn(
            '"title": '
            '"Bounded learning artifact transaction"',
            text,
        )
        self.assertIn(
            "prepare",
            text,
        )
        self.assertIn(
            (
                f"> {self.plan.as_posix()} "
                "<<'TRANSACTION'"
            ),
            text,
        )
        self.assertNotIn(
            "iam-learning-transaction.json",
            text,
        )
        self.assertIn(
            "only stdout payload",
            text,
        )
        self.assertIn(
            "Diagnostics and failures use stderr",
            text,
        )

        self.assertEqual(
            self.repository_files(),
            self.before,
        )
        self.assertFalse(
            (self.root / ".authoring").exists()
        )
        self.assertFalse(
            (self.root / ".private").exists()
        )

    def test_prepare_reads_stdin_and_writes_only_plan_json_to_stdout(
        self,
    ) -> None:
        completed = subprocess.run(
            self.command("prepare"),
            cwd=ROOT,
            input=json.dumps(transaction()),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(
            completed.returncode,
            0,
            msg=completed.stderr,
        )
        self.assertEqual(
            completed.stderr,
            "",
        )

        prepared = json.loads(
            completed.stdout
        )

        self.assertEqual(
            prepared["plan_type"],
            "prepared_learning_transaction",
        )
        self.assertEqual(
            prepared["changes"]["updated"],
            [OBJECT_ID],
        )
        self.assertEqual(
            self.repository_files(),
            self.before,
        )

    def test_dash_has_same_pipe_behavior(
        self,
    ) -> None:
        completed = subprocess.run(
            self.command(
                "prepare",
                "-",
                "-o",
                "-",
            ),
            cwd=ROOT,
            input=json.dumps(transaction()),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(
            completed.returncode,
            0,
            msg=completed.stderr,
        )
        self.assertEqual(
            completed.stderr,
            "",
        )
        self.assertEqual(
            json.loads(
                completed.stdout
            )["changes"]["updated"],
            [OBJECT_ID],
        )

    def test_invalid_stdin_fails_nonzero_with_clean_stdout_and_json_stderr(
        self,
    ) -> None:
        completed = subprocess.run(
            self.command("prepare"),
            cwd=ROOT,
            input='{"schema_version":"1.0"}',
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(
            completed.returncode,
            1,
        )
        self.assertEqual(
            completed.stdout,
            "",
        )

        failure = json.loads(
            completed.stderr
        )

        self.assertEqual(
            failure["failure"]["phase"],
            "prepare",
        )
        self.assertIn(
            "invalid transaction",
            failure["failure"]["reason"],
        )

    def test_prepared_stdout_artifact_drives_non_mutating_dry_run(
        self,
    ) -> None:
        prepared = subprocess.run(
            self.command("prepare"),
            cwd=ROOT,
            input=json.dumps(transaction()),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(
            prepared.returncode,
            0,
            msg=prepared.stderr,
        )

        self.plan.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        self.plan.write_text(
            prepared.stdout,
            encoding="utf-8",
        )

        dry_run = subprocess.run(
            self.command(
                "apply",
                str(self.plan),
            ),
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(
            dry_run.returncode,
            0,
            msg=dry_run.stderr,
        )
        self.assertEqual(
            dry_run.stderr,
            "",
        )
        self.assertEqual(
            json.loads(
                dry_run.stdout
            )["operation"],
            "dry_run",
        )
        self.assertEqual(
            self.repository_files(),
            self.before,
        )


if __name__ == "__main__":
    unittest.main()
