# Bounded learning workflow

The tooling lives on `master`; canonical `content/**` lives in the `backend` worktree. The CLI derives its tooling root from `scripts/content_workflow.py` and accepts only the content workspace explicitly.

The stable workflow is:

```text
chat task -> AI candidate transaction -> prepare immutable plan -> dry-run plan -> human review -> execute same plan
```

## Supported implementation

Increment 1 has one supported bounded-learning workflow:

```text
scripts/content_workflow.py
scripts/learning_workflow/engine.py
schemas/learning-transaction.schema.json
```

The installed command remains:

```text
learning-workflow = "scripts.content_workflow:main"
```

The supported command surface is:

```text
query
chat-task
prepare
apply
```

The earlier packet-oriented `scripts/authoring.py` workflow has been retired.
It is not a supported source-ingestion, transaction, or application path.

This consolidation does not introduce a replacement source-ingestion
workflow, automatic source registration, new learning capability, or new
private-state infrastructure. Any future source-ingestion increment requires
its own bounded design based on an observed learning need.

Persistent interaction artifacts belong under `.dx/`. The workflow must not
introduce persistent `.authoring/` or `.private/` repository infrastructure.

## Generate the chat-ready IAM task

From the frontend worktree:

```bash
mkdir -p .dx

py -X utf8 scripts/content_workflow.py \
  --content-workspace ../aws-learning-curve-backend \
  chat-task \
  --goal "Understand the difference between IAM users, roles, and policies." \
  --id aws.iam.user-vs-role-vs-policy \
  --tag iam \
  --kind concept \
  --status published \
  --status candidate \
  -o .dx/iam-learning-task.md
```

The command reuses the deterministic bounded query. It writes a complete UTF-8 handoff under `.dx/` and does not mutate frontend or backend content. The task embeds the actual bounded context and the authoritative `schemas/learning-transaction.schema.json` contract.

If the requested comparison ID is absent, `missing_ids` records that fact. The AI must not invent an existing target. It may propose a schema-valid `create`, `update`, or `unchanged` operation based only on the supplied context.

Give `.dx/iam-learning-task.md` to the chat AI. The AI returns one complete Git Bash command. That command sends the candidate transaction to `prepare` through UTF-8 stdin and redirects the prepared plan from clean stdout directly to `.dx/iam-prepared-plan.json`:

```bash
mkdir -p .dx
py -X utf8 scripts/content_workflow.py \
  --content-workspace ../aws-learning-curve-backend \
  prepare \
  > .dx/iam-prepared-plan.json <<'TRANSACTION'
{
  "schema_version": "1.0",
  "learning_goal": "Understand the difference between IAM users, roles, and policies.",
  "operations": []
}
TRANSACTION
```

The AI replaces the empty operations array with one complete schema-valid candidate transaction. No intermediate transaction file is required. Successful machine-readable JSON is the only stdout payload. INFO messages and failure JSON use stderr, and failures return a nonzero exit code.

Python validates the existing transaction schema, derives repository paths, assigns system fields, creates `prepared_at` once, and emits a hash-protected plan containing the exact UTF-8 payload bytes. Python also derives a deterministic generation-run ID from the semantic transaction, overwrites any AI-supplied `provenance.transformation.run_id`, and adds a matching `generation_run` payload whose outputs list the created, updated, and unchanged learning-object IDs. Retain this artifact. Do not regenerate it between dry-run and execution.

## Dry-run the prepared plan

```bash
py -X utf8 scripts/content_workflow.py \
  --content-workspace ../aws-learning-curve-backend \
  apply .dx/iam-prepared-plan.json \
  > .dx/iam-dry-run-result.json
```

Dry-run stages backend content with the frontend-owned schemas and scripts, writes the exact prepared payloads there, and runs repository validation. It does not mutate the backend worktree.

Review:

- the candidate transaction;
- the prepared plan;
- the dry-run result;
- the exact planned paths and hashes;
- the current Git state of the backend worktree.

A successful dry-run does not trigger execution.

## Execute the same reviewed plan

Only after human review:

```bash
py -X utf8 scripts/content_workflow.py \
  --content-workspace ../aws-learning-curve-backend \
  apply .dx/iam-prepared-plan.json \
  --execute \
  > .dx/iam-apply-result.json
```

Execution rejects the plan if any target changed after preparation. It writes the exact payload bytes reviewed during dry-run and performs best-effort rollback if writing or validation fails. Multi-file writing is not described as atomic.

Git branch, commit, push, pull request, merge, release, and deployment remain outside this workflow. A successful operation proves repository-tooling success, not learner mastery.

## Human acceptance record

Keep the first acceptance record as a durable `.dx/` working artifact, not as a new private-state subsystem. Record:

```text
learning goal:
context artifact:
prepared plan SHA-256:
dry-run result:
applied or rejected:
short study interaction:
learner-provided unresolved point:
```

The unresolved point must come from the learner after short study use. Python and AI must not infer it as an authoritative fact.


## Register a bounded source

UTF-8 `.txt` and `.md` inputs are registered deterministically in the backend. The command is a dry-run unless `--execute` is supplied. Python normalizes CRLF and CR to LF, removes trailing newlines, derives the canonical `content/sources/<source-id>.yaml` path, fragments Markdown by heading-based sections and plain text by non-empty paragraphs, and owns offsets, hashes, fingerprints, timestamps, and revision fields. Registration creates no generation run.

```bash
py -X utf8 scripts/content_workflow.py \
  --content-workspace ../aws-learning-curve-backend \
  register-source .dx/vpc-notes.md \
  --source-id source.aws.vpc.phase1 \
  --title "Phase 1 VPC notes" \
  --source-type course_notes \
  --language en-US
```

Review the JSON result, then repeat with `--execute`. Re-registering identical normalized content is unchanged; reusing the source ID for different normalized content is rejected. Candidate transactions are checked before preparation so provenance pairs and grounding sets must agree and resolve to canonical registered source fragments with intact fingerprints. Registered source text remains excluded from the public bundle.
