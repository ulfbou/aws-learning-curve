"""Focused tests for deterministic source registration."""
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
SOURCE_ID = "source.aws.vpc.phase1"


class RegistrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.backend = self.root / "backend"
        (self.backend / "content").mkdir(
            parents=True
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def invoke(
        self,
        path: Path,
        *extra: str,
        expected: int = 0,
    ) -> dict:
        completed = subprocess.run(
            [
                sys.executable,
                str(CLI),
                "--content-workspace",
                str(self.backend),
                "register-source",
                str(path),
                "--source-id",
                SOURCE_ID,
                "--title",
                "VPC",
                "--source-type",
                "course_notes",
                "--language",
                "en-US",
                *extra,
            ],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            completed.returncode,
            expected,
            msg=completed.stderr,
        )
        return json.loads(
            completed.stdout or completed.stderr
        )

    def test_markdown_sections_include_preamble_headings_and_exact_offsets(
        self,
    ) -> None:
        source = self.root / "vpc.md"
        source.write_bytes(
            b"Preamble\r\n\r\n"
            b"# VPC\r\n"
            b"CIDR and subnets.\r\n\r\n"
            b"## Routing\r\n"
            b"Route tables.\r\n"
        )

        dry_run = self.invoke(source)
        target = (
            self.backend
            / "content"
            / "sources"
            / f"{SOURCE_ID}.yaml"
        )

        self.assertEqual(
            dry_run["status"],
            "would_create",
        )
        self.assertFalse(target.exists())

        executed = self.invoke(
            source,
            "--execute",
        )
        self.assertTrue(target.is_file())
        self.assertEqual(
            executed["generation_runs_created"],
            0,
        )
        self.assertFalse(
            (
                self.backend
                / "content"
                / "generation-runs"
            ).exists()
        )
        self.assertEqual(
            dry_run["payload_sha256"],
            executed["payload_sha256"],
        )
        self.assertEqual(
            dry_run["source_content_hash"],
            executed["source_content_hash"],
        )

        record = yaml.safe_load(
            target.read_text(encoding="utf-8")
        )
        self.assertEqual(
            [
                fragment.get("heading")
                for fragment in record["fragments"]
            ],
            [None, "VPC", "Routing"],
        )

        normalized = (
            "Preamble\n\n"
            "# VPC\n"
            "CIDR and subnets.\n\n"
            "## Routing\n"
            "Route tables."
        )

        for fragment in record["fragments"]:
            locator = fragment["locator"]
            self.assertEqual(
                normalized[
                    locator["start_offset"]:
                    locator["end_offset"]
                ],
                fragment["exact_text"],
            )

        unchanged = self.invoke(
            source,
            "--execute",
        )
        self.assertEqual(
            unchanged["status"],
            "unchanged",
        )
        self.assertFalse(
            unchanged["executed"]
        )

    def test_plain_text_newlines_final_newline_ids_and_fingerprints_are_deterministic(
        self,
    ) -> None:
        first = self.root / "a.txt"
        second = self.root / "b.txt"

        first.write_bytes(
            b"one\r\n\r\ntwo\r\n"
        )
        second.write_bytes(
            b"one\n\ntwo"
        )

        first_result = self.invoke(first)
        second_result = self.invoke(second)

        self.assertEqual(
            first_result["origin_content_hash"],
            second_result["origin_content_hash"],
        )
        self.assertEqual(
            first_result["fragment_count"],
            2,
        )
        self.assertEqual(
            second_result["fragment_count"],
            2,
        )

    def test_rejects_unsupported_extension_invalid_utf8_empty_input_and_conflict(
        self,
    ) -> None:
        cases = (
            ("x.pdf", b"x", "extension"),
            ("x.md", b"\xff", "UTF-8"),
            ("x.txt", b" \r\n", "empty"),
        )

        for name, data, reason in cases:
            path = self.root / name
            path.write_bytes(data)
            failure = self.invoke(
                path,
                expected=1,
            )
            self.assertIn(
                reason,
                failure["failure"]["reason"],
            )

        source = self.root / "ok.txt"
        source.write_text(
            "first",
            encoding="utf-8",
        )
        self.invoke(
            source,
            "--execute",
        )

        target = (
            self.backend
            / "content"
            / "sources"
            / f"{SOURCE_ID}.yaml"
        )
        original = target.read_bytes()

        source.write_text(
            "different",
            encoding="utf-8",
        )
        failure = self.invoke(
            source,
            "--execute",
            expected=1,
        )
        self.assertIn(
            "different normalized content",
            failure["failure"]["reason"],
        )
        self.assertEqual(
            target.read_bytes(),
            original,
        )


if __name__ == "__main__":
    unittest.main()
