#!/usr/bin/env bash
set -euo pipefail

FRONTEND="$(git rev-parse --show-toplevel)"
BACKEND="${AWS_LEARNING_CURVE_BACKEND:-$FRONTEND/../aws-learning-curve-backend}"
ARTIFACTS="$FRONTEND/.dx/content-increment"
SOURCE="$ARTIFACTS/source.md"
PACKET="$ARTIFACTS/packet.yaml"
TRANSACTION_TEMPLATE="$ARTIFACTS/transaction.yaml"
TRANSACTION="$ARTIFACTS/transaction.resolved.yaml"
RESULT="$FRONTEND/../.dx/content-release-result.txt"
REMOTE="${AWS_LEARNING_CURVE_REMOTE:-origin}"
BACKEND_BRANCH="${AWS_LEARNING_CURVE_BACKEND_BRANCH:-backend}"

mkdir -p "$ARTIFACTS" "$(dirname "$RESULT")"
rm -f "$RESULT"

fail() {
    local phase="$1"
    local exit_code="${2:-1}"

    {
        printf 'CONTENT RELEASE FAILED\n'
        printf 'phase: %s\n' "$phase"
        printf 'exit_code: %s\n' "$exit_code"
        printf 'timestamp_utc: %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
        printf 'frontend: %s\n' "$FRONTEND"
        printf 'backend: %s\n' "$BACKEND"

        printf '\n===== FRONTEND STATUS =====\n'
        git -C "$FRONTEND" status --short --branch 2>&1 || true

        printf '\n===== BACKEND STATUS =====\n'
        git -C "$BACKEND" status --short --branch 2>&1 || true

        for file in "$SOURCE" "$PACKET" "$TRANSACTION_TEMPLATE" "$TRANSACTION"; do
            printf '\n===== %s =====\n' "$file"
            if [[ -f "$file" ]]; then
                cat "$file"
            else
                printf '[missing]\n'
            fi
        done
    } >"$RESULT"

    printf '\nCONTENT RELEASE FAILED\n' >&2
    printf 'Upload this file to the AI:\n  %s\n' "$RESULT" >&2
    exit "$exit_code"
}

trap 'fail "unexpected-command-failure" "$?"' ERR

cd "$FRONTEND"

if [[ ! -f scripts/authoring.py ]]; then
    fail "missing-authoring-script" 2
fi

if [[ ! -d "$BACKEND/.git" && ! -f "$BACKEND/.git" ]]; then
    git fetch "$REMOTE" "$BACKEND_BRANCH"

    if ! git show-ref --verify --quiet "refs/heads/$BACKEND_BRANCH"; then
        git branch "$BACKEND_BRANCH" "$REMOTE/$BACKEND_BRANCH"
    fi

    git worktree add "$BACKEND" "$BACKEND_BRANCH"
fi

if [[ ! -d "$BACKEND/content" ]]; then
    fail "missing-backend-content" 2
fi

if [[ ! -f "$SOURCE" || ! -f "$TRANSACTION_TEMPLATE" ]]; then
    fail "missing-increment-payload" 2
fi

py -X utf8 scripts/authoring.py ingest \
    --input "$SOURCE" \
    --source-id source.test.dummy-authoring \
    --source-type own_notes \
    --source-metadata forbidden \
    --title "Dummy authoring source" \
    --language en-US \
    --output "$PACKET"

py -X utf8 - "$PACKET" "$TRANSACTION_TEMPLATE" "$TRANSACTION" <<'PY'
from pathlib import Path
import sys
import yaml

packet_path = Path(sys.argv[1])
template_path = Path(sys.argv[2])
transaction_path = Path(sys.argv[3])

packet = yaml.safe_load(packet_path.read_text(encoding="utf-8"))
packet_hash = packet.get("packet_hash")

if not isinstance(packet_hash, str) or not packet_hash.startswith("sha256:"):
    raise SystemExit("Generated packet has no valid packet_hash")

template = template_path.read_text(encoding="utf-8")

if template.count("__PACKET_HASH__") != 1:
    raise SystemExit("Transaction template must contain one __PACKET_HASH__ marker")

transaction_path.write_text(
    template.replace("__PACKET_HASH__", packet_hash),
    encoding="utf-8",
    newline="\n",
)
PY

py -X utf8 scripts/authoring.py apply \
    --transaction "$TRANSACTION" \
    --packet "$PACKET" \
    --backend "$BACKEND" \
    --dry-run

py -X utf8 scripts/authoring.py apply \
    --transaction "$TRANSACTION" \
    --packet "$PACKET" \
    --backend "$BACKEND"

py -X utf8 scripts/validate_content.py \
    --root "$BACKEND"

trap - ERR

{
    printf 'CONTENT RELEASE PASSED\n'
    printf 'timestamp_utc: %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
    printf 'frontend: %s\n' "$FRONTEND"
    printf 'backend: %s\n' "$BACKEND"
    printf 'transaction: %s\n' "$TRANSACTION"

    printf '\n===== BACKEND STATUS =====\n'
    git -C "$BACKEND" status --short --branch

    printf '\n===== BACKEND CONTENT DIFF =====\n'
    git -C "$BACKEND" diff -- content
    git -C "$BACKEND" diff --cached -- content
} >"$RESULT"

printf '\nCONTENT RELEASE PASSED\n'
printf 'The candidate increment was applied and validated.\n'
printf 'No upload is needed.\n'
printf 'Result: %s\n' "$RESULT"
