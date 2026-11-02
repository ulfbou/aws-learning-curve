#!/usr/bin/env python3
"""Run and independently validate a complete AWS Learning Curve release."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


class ValidationError(RuntimeError):
    pass


def command_path(name: str) -> str:
    path = shutil.which(name)

    if path is None:
        raise ValidationError(
            f"required command not found on PATH: {name}"
        )

    return path


def run(
    command: list[str],
    *,
    cwd: Path,
    capture: bool = False,
) -> str:
    printable = subprocess.list2cmdline(command)

    print(
        f"[validate-release] {printable}",
        flush=True,
    )

    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            capture_output=capture,
            check=False,
        )
    except OSError as error:
        raise ValidationError(
            f"could not start {printable}: {error}"
        ) from error

    if result.returncode != 0:
        detail = ""

        if capture:
            detail = (
                result.stderr
                or result.stdout
            ).strip()

        suffix = f"\n{detail}" if detail else ""

        raise ValidationError(
            f"command failed ({result.returncode}): "
            f"{printable}{suffix}"
        )

    return result.stdout.strip() if capture else ""


def git(
    *args: str,
    cwd: Path,
) -> str:
    return run(
        [
            command_path("git"),
            *args,
        ],
        cwd=cwd,
        capture=True,
    )


def require_file(
    path: Path,
    *,
    allow_empty: bool = False,
) -> None:
    if not path.is_file():
        raise ValidationError(
            f"missing file: {path}"
        )

    if (
        not allow_empty
        and path.stat().st_size == 0
    ):
        raise ValidationError(
            f"empty file: {path}"
        )


def validate_inputs(
    frontend: Path,
    backend: Path,
) -> None:
    if not (frontend / ".git").exists():
        raise ValidationError(
            f"frontend is not a Git workspace: {frontend}"
        )

    if not (backend / ".git").exists():
        raise ValidationError(
            f"backend is not a Git workspace: {backend}"
        )

    required_frontend = (
        "package.json",
        "package-lock.json",
        "requirements.txt",
        "scripts/release.py",
        "scripts/validate_content.py",
        "scripts/build_learning_bundle.py",
        "scripts/verify_pages.py",
        "public/index.html",
        "public/app.js",
        "public/favicon.svg",
        "public/.nojekyll",
        "src/tailwind.css",
        "tailwind.config.js",
    )

    for relative in required_frontend:
        require_file(
            frontend / relative,
            allow_empty=(
                relative == "public/.nojekyll"
            ),
        )

    if not (backend / "content").is_dir():
        raise ValidationError(
            f"backend content directory is missing: "
            f"{backend / 'content'}"
        )

    tracked = [
        item
        for item in git(
            "ls-files",
            "-z",
            cwd=backend,
        ).split("\0")
        if item
    ]

    outside_content = sorted(
        item
        for item in tracked
        if not item.startswith("content/")
    )

    if outside_content:
        raise ValidationError(
            "backend tracks files outside content/**:\n"
            + "\n".join(outside_content)
        )

    for name in (
        "git",
        "node",
        "npm",
    ):
        resolved = command_path(name)

        print(
            f"[validate-release] "
            f"{name}: {resolved}"
        )


def compile_python(
    frontend: Path,
) -> None:
    scripts = sorted(
        (frontend / "scripts").glob("*.py")
    )

    if not scripts:
        raise ValidationError(
            "no Python scripts found under scripts/"
        )

    run(
        [
            sys.executable,
            "-m",
            "py_compile",
            *map(str, scripts),
        ],
        cwd=frontend,
    )


def validate_artifact(
    artifact: Path,
    frontend: Path,
    backend: Path,
) -> None:
    required = (
        ("index.html", False),
        ("app.js", False),
        ("styles.css", False),
        ("favicon.svg", False),
        (".nojekyll", True),
        (
            "data/learning-bundle.json",
            False,
        ),
        (
            "data/learning-bundle.manifest.json",
            False,
        ),
        (
            "data/release.json",
            False,
        ),
    )

    for relative, allow_empty in required:
        require_file(
            artifact / relative,
            allow_empty=allow_empty,
        )

    bundle_path = (
        artifact
        / "data"
        / "learning-bundle.json"
    )

    manifest_path = (
        artifact
        / "data"
        / "learning-bundle.manifest.json"
    )

    release_path = (
        artifact
        / "data"
        / "release.json"
    )

    bundle_text = bundle_path.read_text(
        encoding="utf-8"
    )

    bundle = json.loads(bundle_text)

    manifest = json.loads(
        manifest_path.read_text(
            encoding="utf-8"
        )
    )

    release = json.loads(
        release_path.read_text(
            encoding="utf-8"
        )
    )

    digest = hashlib.sha256(
        bundle_text.encode("utf-8")
    ).hexdigest()

    if manifest.get("bundleHash") != digest:
        raise ValidationError(
            "manifest bundleHash does not "
            "match bundle bytes"
        )

    if (
        bundle.get("contentVersion")
        != manifest.get("contentVersion")
    ):
        raise ValidationError(
            "bundle and manifest "
            "contentVersion differ"
        )

    expected_frontend = git(
        "rev-parse",
        "HEAD",
        cwd=frontend,
    )

    expected_backend = git(
        "rev-parse",
        "HEAD",
        cwd=backend,
    )

    if (
        release.get("frontendCommit")
        != expected_frontend
    ):
        raise ValidationError(
            "release.json frontendCommit "
            "is incorrect"
        )

    if (
        release.get("backendCommit")
        != expected_backend
    ):
        raise ValidationError(
            "release.json backendCommit "
            "is incorrect"
        )

    print(
        "[validate-release] PASS "
        f"contentVersion="
        f"{manifest['contentVersion']} "
        f"bundleHash={digest} "
        f"frontendCommit={expected_frontend} "
        f"backendCommit={expected_backend}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Execute scripts/release.py in an "
            "isolated output directory and "
            "independently validate the "
            "produced artifact."
        )
    )

    parser.add_argument(
        "--frontend",
        type=Path,
        default=(
            Path(__file__)
            .resolve()
            .parents[1]
        ),
    )

    parser.add_argument(
        "--backend",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--keep",
        type=Path,
        help=(
            "copy the validated artifact "
            "to this path after validation"
        ),
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    frontend = (
        args.frontend
        .expanduser()
        .resolve()
    )

    backend = (
        args.backend
        .expanduser()
        .resolve()
    )

    validate_inputs(
        frontend,
        backend,
    )

    compile_python(frontend)

    with tempfile.TemporaryDirectory(
        prefix=(
            "aws-learning-curve-validation-"
        )
    ) as temp:
        output = Path(temp) / "release"

        run(
            [
                sys.executable,
                str(
                    frontend
                    / "scripts"
                    / "release.py"
                ),
                "--ci",
                "--frontend",
                str(frontend),
                "--backend",
                str(backend),
                "--output",
                str(output),
            ],
            cwd=frontend,
        )

        validate_artifact(
            output,
            frontend,
            backend,
        )

        if args.keep:
            destination = (
                args.keep
                .expanduser()
                .resolve()
            )

            if destination.exists():
                shutil.rmtree(destination)

            destination.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            shutil.copytree(
                output,
                destination,
            )

            print(
                "[validate-release] "
                f"retained artifact: "
                f"{destination}"
            )

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as error:
        print(
            f"release validation failed: {error}",
            file=sys.stderr,
        )
        raise SystemExit(1)
