"""Verify the complete GitHub Pages release artifact."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
DATA = PUBLIC / "data"

FORBIDDEN_PUBLIC_KEYS = {
    "exact_text",
    "normalized_text",
    "content_fingerprint",
    "locator",
    "learner_id",
    "fsrs_parameters",
    "attempts",
    "events",
}

FORBIDDEN_PUBLIC_MARKERS = {
    ".dx/",
    ".private/",
    ".authoring/",
}


def fail(message: str) -> None:
    raise SystemExit(
        f"Pages verification failed: {message}"
    )


def require_file(
    path: Path,
    *,
    allow_empty: bool = False,
) -> None:
    if not path.is_file():
        fail(
            f"missing file: "
            f"{path.relative_to(ROOT)}"
        )

    if (
        not allow_empty
        and path.stat().st_size == 0
    ):
        fail(
            f"empty file: "
            f"{path.relative_to(ROOT)}"
        )


def collect_public_boundary_violations(
    value: Any,
    *,
    location: str = "<root>",
) -> list[str]:
    violations: list[str] = []

    if isinstance(value, dict):
        for key, child in value.items():
            child_location = (
                f"{location}.{key}"
            )

            if key in FORBIDDEN_PUBLIC_KEYS:
                violations.append(
                    f"{child_location}: "
                    f"forbidden public field"
                )

            if (
                key == "origin"
                and isinstance(child, dict)
                and "path" in child
            ):
                violations.append(
                    f"{child_location}.path: "
                    "local source path"
                )

            violations.extend(
                collect_public_boundary_violations(
                    child,
                    location=child_location,
                )
            )

    elif isinstance(value, list):
        for index, child in enumerate(value):
            violations.extend(
                collect_public_boundary_violations(
                    child,
                    location=(
                        f"{location}[{index}]"
                    ),
                )
            )

    elif isinstance(value, str):
        normalized = value.replace(
            "\\",
            "/",
        )

        for marker in FORBIDDEN_PUBLIC_MARKERS:
            if marker in normalized:
                violations.append(
                    f"{location}: "
                    f"forbidden marker {marker!r}"
                )

    return violations


def validate_public_data_boundary(
    data_directory: Path,
) -> None:
    for path in sorted(
        data_directory.rglob("*.json")
    ):
        try:
            document = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )
        except json.JSONDecodeError as error:
            fail(
                f"invalid JSON in "
                f"{path.relative_to(ROOT)}: "
                f"{error}"
            )

        violations = (
            collect_public_boundary_violations(
                document,
                location=path.name,
            )
        )

        if violations:
            fail(
                "public-content boundary violation:\n"
                + "\n".join(violations)
            )


def main() -> None:
    required = [
        (PUBLIC / "index.html", False),
        (PUBLIC / "app.js", False),
        (PUBLIC / "styles.css", False),
        (PUBLIC / "favicon.svg", False),
        (PUBLIC / ".nojekyll", True),
        (
            DATA
            / "learning-bundle.json",
            False,
        ),
        (
            DATA
            / "learning-bundle.manifest.json",
            False,
        ),
    ]

    for path, allow_empty in required:
        require_file(
            path,
            allow_empty=allow_empty,
        )

    index = (
        PUBLIC
        / "index.html"
    ).read_text(encoding="utf-8")
    app = (
        PUBLIC
        / "app.js"
    ).read_text(encoding="utf-8")
    styles = (
        PUBLIC
        / "styles.css"
    ).read_text(encoding="utf-8")

    if "cdn.tailwindcss.com" in index:
        fail(
            "public/index.html still uses "
            "the Tailwind browser CDN"
        )

    if 'href="./styles.css"' not in index:
        fail(
            "public/index.html does not "
            "load ./styles.css"
        )

    if 'href="./favicon.svg"' not in index:
        fail(
            "public/index.html does not "
            "load ./favicon.svg"
        )

    if (
        '<script type="module" '
        'src="./app.js"></script>'
        not in index
    ):
        fail(
            "public/index.html does not "
            "load ./app.js as a module"
        )

    mojibake_markers = (
        "Ã",
        "Â",
        "â€¦",
        "â€“",
        "â€¢",
    )

    for marker in mojibake_markers:
        if marker in app:
            fail(
                "public/app.js contains "
                "possible UTF-8 mojibake "
                f"marker: {marker!r}"
            )

    if len(styles.strip()) < 100:
        fail(
            "public/styles.css does not "
            "appear to contain compiled CSS"
        )

    syntax_check = subprocess.run(
        [
            "node",
            "--check",
            str(PUBLIC / "app.js"),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    if syntax_check.returncode != 0:
        details = (
            syntax_check.stderr.strip()
            or syntax_check.stdout.strip()
        )
        fail(
            "public/app.js syntax error:\n"
            f"{details}"
        )

    bundle_path = (
        DATA
        / "learning-bundle.json"
    )
    manifest_path = (
        DATA
        / "learning-bundle.manifest.json"
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

    if bundle.get("sources") != {}:
        fail(
            "public bundle must retain an "
            "empty compatibility sources collection"
        )

    if (
        bundle.get("contentVersion")
        != manifest.get("contentVersion")
    ):
        fail(
            "bundle and manifest "
            "contentVersion differ"
        )

    digest = hashlib.sha256(
        bundle_text.encode("utf-8")
    ).hexdigest()

    if digest != manifest.get(
        "bundleHash"
    ):
        fail(
            "bundleHash does not match "
            "learning-bundle.json"
        )

    validate_public_data_boundary(DATA)

    obsolete = PUBLIC / "wwwroot"

    if obsolete.exists():
        fail(
            "obsolete public/wwwroot "
            "directory is still present"
        )

    print(
        "Pages artifact verified: "
        f"{manifest['contentVersion']} "
        f"{digest[:12]}..."
    )


if __name__ == "__main__":
    main()
