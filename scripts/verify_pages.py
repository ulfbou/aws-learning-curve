"""Verify the complete GitHub Pages release artifact."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
DATA = PUBLIC / "data"


def fail(message: str) -> None:
    raise SystemExit(f"Pages verification failed: {message}")


def require_file(path: Path, *, allow_empty: bool = False) -> None:
    if not path.is_file():
        fail(f"missing file: {path.relative_to(ROOT)}")

    if not allow_empty and path.stat().st_size == 0:
        fail(f"empty file: {path.relative_to(ROOT)}")


def main() -> None:
    required = [
        (PUBLIC / "index.html", False),
        (PUBLIC / "app.js", False),
        (PUBLIC / "styles.css", False),
        (PUBLIC / ".nojekyll", True),
        (DATA / "learning-bundle.json", False),
        (DATA / "learning-bundle.manifest.json", False),
    ]

    for path, allow_empty in required:
        require_file(path, allow_empty=allow_empty)

    index = (PUBLIC / "index.html").read_text(encoding="utf-8")
    app = (PUBLIC / "app.js").read_text(encoding="utf-8")
    styles = (PUBLIC / "styles.css").read_text(encoding="utf-8")

    if "cdn.tailwindcss.com" in index:
        fail("public/index.html still uses the Tailwind browser CDN")

    if 'href="./styles.css"' not in index:
        fail("public/index.html does not load ./styles.css")

    if '<script type="module" src="./app.js"></script>' not in index:
        fail("public/index.html does not load ./app.js as a module")

    mojibake_markers = ("Ã", "Â", "â€¦", "â€“", "â€¢")

    for marker in mojibake_markers:
        if marker in app:
            fail(
                "public/app.js contains possible UTF-8 mojibake marker: "
                f"{marker!r}"
            )

    if len(styles.strip()) < 100:
        fail("public/styles.css does not appear to contain compiled CSS")

    syntax_check = subprocess.run(
        ["node", "--check", str(PUBLIC / "app.js")],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    if syntax_check.returncode != 0:
        details = syntax_check.stderr.strip() or syntax_check.stdout.strip()
        fail(f"public/app.js syntax error:\n{details}")

    bundle_path = DATA / "learning-bundle.json"
    manifest_path = DATA / "learning-bundle.manifest.json"

    bundle_text = bundle_path.read_text(encoding="utf-8")
    bundle = json.loads(bundle_text)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    if bundle.get("contentVersion") != manifest.get("contentVersion"):
        fail("bundle and manifest contentVersion differ")

    digest = hashlib.sha256(bundle_text.encode("utf-8")).hexdigest()

    if digest != manifest.get("bundleHash"):
        fail("bundleHash does not match learning-bundle.json")

    obsolete = PUBLIC / "wwwroot"

    if obsolete.exists():
        fail("obsolete public/wwwroot directory is still present")

    print(
        "Pages artifact verified: "
        f"{manifest['contentVersion']} {digest[:12]}..."
    )


if __name__ == "__main__":
    main()
