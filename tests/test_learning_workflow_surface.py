"""Regression guards for the supported bounded-learning workflow surface."""

from __future__ import annotations

import ast
import tomllib
import unittest
from pathlib import Path

from scripts import content_workflow


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

SUPPORTED_COMMANDS = {
    "register-source",
    "query",
    "chat-task",
    "prepare",
    "apply",
}

RETIRED_MODULES = {
    "authoring",
    "authoring_common",
}


def imported_modules(path: Path) -> set[str]:
    """Return module names imported by one Python source file."""
    tree = ast.parse(
        path.read_text(encoding="utf-8"),
        filename=str(path),
    )
    modules: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)

    return modules


class LearningWorkflowSurfaceTests(unittest.TestCase):
    def test_supported_command_surface_is_stable(self) -> None:
        parser = content_workflow.parser()
        subparsers = [
            action
            for action in parser._actions
            if isinstance(getattr(action, "choices", None), dict)
            and action.choices
        ]

        self.assertEqual(
            len(subparsers),
            1,
            msg="Expected exactly one CLI subparser action.",
        )
        self.assertEqual(
            set(subparsers[0].choices),
            SUPPORTED_COMMANDS,
        )

    def test_chat_task_defaults_use_dx_workspace(self) -> None:
        args = content_workflow.parser().parse_args(
            [
                "--content-workspace",
                "backend",
                "chat-task",
                "--goal",
                "Understand IAM roles.",
            ]
        )

        self.assertEqual(
            args.output,
            Path(".dx/iam-learning-task.md"),
        )
        self.assertEqual(
            args.prepared_plan_output,
            Path(".dx/iam-prepared-plan.json"),
        )
        self.assertEqual(
            args.dry_run_output,
            Path(".dx/iam-dry-run-result.json"),
        )
        self.assertEqual(
            args.apply_output,
            Path(".dx/iam-apply-result.json"),
        )

        for path in (
            args.output,
            args.prepared_plan_output,
            args.dry_run_output,
            args.apply_output,
        ):
            self.assertEqual(path.parts[0], ".dx")

    def test_retired_authoring_modules_do_not_exist(self) -> None:
        for module in RETIRED_MODULES:
            path = SCRIPTS / f"{module}.py"
            self.assertFalse(
                path.exists(),
                msg=f"Retired workflow module still exists: {path}",
            )

    def test_supported_workflow_does_not_import_retired_modules(
        self,
    ) -> None:
        supported_sources = [
            SCRIPTS / "content_workflow.py",
            *sorted(
                (SCRIPTS / "learning_workflow").glob("*.py")
            ),
        ]

        violations: list[str] = []

        for path in supported_sources:
            for module in imported_modules(path):
                parts = module.split(".")
                if any(part in RETIRED_MODULES for part in parts):
                    violations.append(
                        f"{path.relative_to(ROOT)} imports {module}"
                    )

        self.assertEqual(
            violations,
            [],
            msg=(
                "Supported workflow imports retired modules:\n"
                + "\n".join(violations)
            ),
        )

    def test_gitignore_keeps_only_supported_workspace_convention(
        self,
    ) -> None:
        entries = {
            line.strip()
            for line in (
                ROOT / ".gitignore"
            ).read_text(
                encoding="utf-8"
            ).splitlines()
            if line.strip()
            and not line.lstrip().startswith("#")
        }

        self.assertIn(".dx/", entries)
        self.assertNotIn(".authoring/", entries)
        self.assertNotIn(".private/", entries)

    def test_package_entry_point_remains_supported_cli(self) -> None:
        project = tomllib.loads(
            (ROOT / "pyproject.toml").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(
            project["project"]["scripts"]["learning-workflow"],
            "scripts.content_workflow:main",
        )


if __name__ == "__main__":
    unittest.main()
