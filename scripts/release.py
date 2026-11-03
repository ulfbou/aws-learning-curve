#!/usr/bin/env python3
"""Assemble and verify one transactional frontend + backend release."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ReleaseError(RuntimeError):
    pass


def resolved_command(command: tuple[str, ...]) -> list[str]:
    executable = shutil.which(command[0])
    if executable is None:
        raise ReleaseError(
            f"required command not found on PATH: {command[0]}"
        )

    resolved = [executable, *command[1:]]

    if (
        os.name == "nt"
        and Path(executable).suffix.lower() in {".cmd", ".bat"}
    ):
        command_processor = (
            os.environ.get("COMSPEC")
            or shutil.which("cmd.exe")
        )

        if command_processor is None:
            raise ReleaseError(
                "Windows command processor not found"
            )

        return [
            command_processor,
            "/d",
            "/s",
            "/c",
            subprocess.list2cmdline(resolved),
        ]

    return resolved


def subprocess_environment() -> dict[str, str]:
    """Return a subprocess environment with explicit UTF-8 text handling."""
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    return environment


def run(*command: str, cwd: Path) -> None:
    resolved = resolved_command(command)
    print(f"[release] {' '.join(resolved)}", flush=True)

    try:
        result = subprocess.run(
            resolved,
            cwd=cwd,
            env=subprocess_environment(),
            check=False,
        )
    except OSError as error:
        raise ReleaseError(
            f"could not start command: "
            f"{' '.join(resolved)}: {error}"
        ) from error

    if result.returncode:
        raise ReleaseError(
            f"command failed ({result.returncode}): "
            f"{' '.join(resolved)}"
        )


def capture(*command: str, cwd: Path) -> str:
    resolved = resolved_command(command)

    try:
        result = subprocess.run(
            resolved,
            cwd=cwd,
            env=subprocess_environment(),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
    except OSError as error:
        raise ReleaseError(
            f"could not start command: "
            f"{' '.join(resolved)}: {error}"
        ) from error

    if result.returncode:
        detail = (
            result.stderr.strip()
            or result.stdout.strip()
        )

        raise ReleaseError(
            f"command failed: {' '.join(resolved)}\n"
            f"{detail}"
        )

    return result.stdout.strip()


def discover_backend(frontend: Path) -> Path:
    configured = os.environ.get(
        "AWS_LEARNING_CURVE_BACKEND"
    )

    if configured:
        return Path(
            configured
        ).expanduser().resolve()

    worktrees = capture(
        "git",
        "worktree",
        "list",
        "--porcelain",
        cwd=frontend,
    )

    path: Path | None = None

    for line in worktrees.splitlines():
        if line.startswith("worktree "):
            path = Path(line[9:]).resolve()
        elif (
            line == "branch refs/heads/backend"
            and path
        ):
            return path

    for candidate in (
        frontend.parent / f"{frontend.name}-backend",
        frontend.parent / "backend",
    ):
        if (candidate / "content").is_dir():
            return candidate.resolve()

    raise ReleaseError(
        "backend workspace not found; provide --backend"
    )


def validate_inputs(
    frontend: Path,
    backend: Path,
) -> None:
    required = (
        "package.json",
        "package-lock.json",
        "requirements.txt",
        "scripts/validate_content.py",
        "scripts/build_learning_bundle.py",
        "scripts/verify_pages.py",
        "public/index.html",
    )

    missing = [
        name
        for name in required
        if not (frontend / name).is_file()
    ]

    if missing:
        raise ReleaseError(
            "missing frontend files: "
            + ", ".join(missing)
        )

    if not (backend / "content").is_dir():
        raise ReleaseError(
            f"backend content directory is missing: "
            f"{backend / 'content'}"
        )

    tracked = capture(
        "git",
        "ls-files",
        "-z",
        cwd=backend,
    ).split("\0")

    invalid = sorted(
        name
        for name in tracked
        if name
        and not name.startswith("content/")
    )

    if invalid:
        raise ReleaseError(
            "backend tracks paths outside content/**:\n"
            + "\n".join(invalid)
        )


def copy_frontend(
    frontend: Path,
    workspace: Path,
) -> None:
    frontend = frontend.resolve()

    def ignore(
        directory: str,
        names: list[str],
    ):
        directory_path = Path(directory).resolve()
        excluded = {"__pycache__"} & set(names)

        if directory_path == frontend:
            excluded |= {
                ".git",
                ".release",
                "content",
                "node_modules",
            } & set(names)

        if directory_path == frontend / "public":
            excluded |= {
                "data",
                "styles.css",
            } & set(names)

        return excluded

    shutil.copytree(
        frontend,
        workspace,
        ignore=ignore,
    )


def build(workspace: Path) -> None:
    run(
        sys.executable,
        "scripts/validate_content.py",
        cwd=workspace,
    )

    run(
        sys.executable,
        "scripts/build_learning_bundle.py",
        cwd=workspace,
    )

    run(
        "npm",
        "ci",
        cwd=workspace,
    )

    run(
        "npm",
        "run",
        "build:css",
        cwd=workspace,
    )

    run(
        "node",
        "--check",
        "public/app.js",
        cwd=workspace,
    )

    run(
        sys.executable,
        "scripts/verify_pages.py",
        cwd=workspace,
    )


def write_release_metadata(
    artifact: Path,
    frontend: Path,
    backend: Path,
) -> None:
    metadata = {
        "schemaVersion": "1.0",
        "frontendCommit": capture(
            "git",
            "rev-parse",
            "HEAD",
            cwd=frontend,
        ),
        "backendCommit": capture(
            "git",
            "rev-parse",
            "HEAD",
            cwd=backend,
        ),
    }

    destination = (
        artifact
        / "data"
        / "release.json"
    )

    destination.write_text(
        json.dumps(
            metadata,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )


def promote(
    candidate: Path,
    output: Path,
) -> None:
    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    previous = output.with_name(
        output.name + ".previous"
    )

    if previous.exists():
        shutil.rmtree(previous)

    if output.exists():
        output.rename(previous)

    try:
        candidate.rename(output)
    except Exception:
        if (
            previous.exists()
            and not output.exists()
        ):
            previous.rename(output)
        raise

    if previous.exists():
        shutil.rmtree(previous)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--ci",
        action="store_true",
    )

    parser.add_argument(
        "--frontend",
        type=Path,
    )

    parser.add_argument(
        "--backend",
        type=Path,
    )

    parser.add_argument(
        "--output",
        type=Path,
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    frontend = (
        args.frontend or ROOT
    ).expanduser().resolve()

    if args.ci and not all(
        (
            args.frontend,
            args.backend,
            args.output,
        )
    ):
        raise ReleaseError(
            "--ci requires --frontend, "
            "--backend, and --output"
        )

    backend = (
        args.backend.expanduser().resolve()
        if args.backend
        else discover_backend(frontend)
    )

    output = (
        args.output.expanduser().resolve()
        if args.output
        else frontend / ".release" / "site"
    )

    validate_inputs(
        frontend,
        backend,
    )

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    transaction = Path(
        tempfile.mkdtemp(
            prefix=".release-",
            dir=output.parent,
        )
    )

    workspace = transaction / "workspace"
    candidate = transaction / "candidate"

    try:
        copy_frontend(
            frontend,
            workspace,
        )

        shutil.copytree(
            backend / "content",
            workspace / "content",
        )

        (
            workspace
            / "public"
            / "data"
        ).mkdir(
            parents=True,
            exist_ok=True,
        )

        build(workspace)

        shutil.copytree(
            workspace / "public",
            candidate,
        )

        write_release_metadata(
            candidate,
            frontend,
            backend,
        )

        promote(
            candidate,
            output,
        )
    finally:
        shutil.rmtree(
            transaction,
            ignore_errors=True,
        )

    result = {
        "status": "success",
        "artifact": str(output),
        "frontendCommit": capture(
            "git",
            "rev-parse",
            "HEAD",
            cwd=frontend,
        ),
        "backendCommit": capture(
            "git",
            "rev-parse",
            "HEAD",
            cwd=backend,
        ),
    }

    print(
        json.dumps(result)
        if args.ci
        else (
            f"[release] verified artifact: "
            f"{output}"
        )
    )

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ReleaseError as error:
        print(
            f"release failed: {error}",
            file=sys.stderr,
        )
        raise SystemExit(1)
