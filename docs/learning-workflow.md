# Bounded learning workflow

The workflow has three repository operations:

```text
query -> prepare -> apply
```

`apply` is a dry-run unless `--execute` is supplied.

## 1. Create bounded context

```bash
py scripts/content_workflow.py --workspace . query \
  --goal "Understand the difference between IAM users, roles, and policies" \
  --keyword IAM \
  --tag iam \
  --kind concept \
  --kind misconception \
  --kind question \
  --status published \
  --status candidate \
  -o .dx/iam-learning-context.json
```

The result contains exact repository objects, direct relationships, revisions,
content hashes, and file hashes. It does not authorize a repository change.

## 2. Ask AI for one candidate transaction

The AI response must conform to `schemas/learning-transaction.schema.json`.
Python derives paths and system fields. The AI supplies semantic content only.

```json
{
  "schema_version": "1.0",
  "learning_goal": "Understand the difference between IAM users, roles, and policies",
  "operations": [
    {
      "action": "update",
      "id": "aws.iam.role",
      "kind": "concept",
      "expected_revision": 1,
      "expected_content_hash": "<64 lowercase hex characters from the context>",
      "content": {
        "schema_version": "1.0",
        "status": "candidate",
        "domain": "aws-cloud",
        "labels": {"en": {"preferred": "IAM role"}},
        "definition": {"en": "A proposed improved learning definition."},
        "provenance": {},
        "grounding": {},
        "aliases": []
      }
    }
  ]
}
```

The semantic content still has to satisfy the repository's object schema and
source policy. System-managed values in `content` are ignored.

## 3. Prepare

```bash
py scripts/content_workflow.py --workspace . prepare \
  .dx/iam-learning-transaction.json \
  -o .dx/iam-prepare-result.json
```

This checks the transaction contract, target identity, kind, revision, content
hash, and derived repository path. It does not write files.

## 4. Dry-run

```bash
py scripts/content_workflow.py --workspace . apply \
  .dx/iam-learning-transaction.json \
  -o .dx/iam-dry-run-result.json
```

The dry-run copies `content/`, `schemas/`, and `scripts/` to a temporary
workspace, applies the planned files there, and runs the repository validator.

## 5. Apply after review

```bash
py scripts/content_workflow.py --workspace . apply \
  .dx/iam-learning-transaction.json \
  --execute \
  -o .dx/iam-apply-result.json
```

Apply writes the planned files and runs repository validation. If writing or
validation fails, the workflow performs best-effort rollback of files changed
by that operation. A multi-file write is not described as atomic.

Git branch, commit, push, pull request, merge, release, and deployment remain
outside this learning workflow.

## 6. Use the artifact

A successful operation result proves only that repository tooling completed.
It does not prove learning.

Use the changed artifact in a short study session and explicitly record the
remaining uncertainty, for example:

```text
I now understand role assumption, but trust policies are still unclear.
```

Use that unresolved point as the next learning need.
