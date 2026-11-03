# Bounded learning workflow

The tooling lives on `master`; canonical `content/**` lives in the `backend` worktree. The CLI derives its tooling root from `scripts/content_workflow.py` and accepts only the content workspace explicitly.

The stable workflow is:

```text
query -> candidate transaction -> prepare immutable plan -> dry-run plan -> execute same plan
```

## Query

```bash
py scripts/content_workflow.py \
  --content-workspace ../aws-learning-curve-backend \
  query \
  --goal "Understand the difference between IAM users, roles, and policies" \
  --id aws.iam.user-vs-role-vs-policy \
  --kind concept \
  --status published \
  --status candidate \
  -o .dx/iam-learning-context.json
```

The result contains backend objects and direct relationships. Paths are repository-derived and remain under the backend `content/` tree.

## Candidate transaction

The AI returns semantic content conforming to `schemas/learning-transaction.schema.json`. It does not assign paths or authoritative revision, timestamp, or hash fields.

## Prepare once

```bash
py scripts/content_workflow.py \
  --content-workspace ../aws-learning-curve-backend \
  prepare .dx/iam-learning-transaction.json \
  -o .dx/iam-prepared-plan.json
```

Python creates `prepared_at` once and emits a hash-protected prepared plan containing exact UTF-8 payload bytes. Review and retain this artifact. Do not regenerate it between dry-run and execute.

## Dry-run the prepared plan

```bash
py scripts/content_workflow.py \
  --content-workspace ../aws-learning-curve-backend \
  apply .dx/iam-prepared-plan.json \
  -o .dx/iam-dry-run-result.json
```

Dry-run stages backend content with tooling-owned schemas and scripts, writes the exact prepared payloads there, and runs the repository validator. It does not mutate the backend worktree.

## Execute the same plan

```bash
py scripts/content_workflow.py \
  --content-workspace ../aws-learning-curve-backend \
  apply .dx/iam-prepared-plan.json \
  --execute \
  -o .dx/iam-apply-result.json
```

Execution rejects the plan if any target changed after preparation. It writes the exact payload bytes reviewed during dry-run and performs best-effort rollback if writing or validation fails. Multi-file writing is not described as atomic.

Git branch, commit, push, PR, merge, release, and deployment remain outside this workflow. A successful operation proves repository-tooling success, not learner mastery.
