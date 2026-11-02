# aws-learning-curve

Frontend and tooling for AWS Learning Curve. Authored learning content is stored
separately on the orphan `backend` branch under `content/**`.

## Ownership

- `master` owns the frontend, schemas, Python tooling, and CI/CD policy.
- `backend` owns only `content/**`.
- `public/data/**` is generated during each release transaction and is never
  committed.

## Transactional release

`scripts/release.py` is the shared local and CI release entry point. It combines
one frontend commit with one backend commit in an isolated workspace, validates
the content, generates the public data, builds the frontend, verifies the
complete Pages artifact, and promotes the artifact only after every step
succeeds.

Local mode discovers a `backend` worktree or accepts `--backend`:

```bash
py scripts/release.py --backend ../aws-learning-curve-backend
```

CI mode requires explicit workspaces and output:

```bash
python scripts/release.py \
  --ci \
  --frontend frontend \
  --backend backend \
  --output release
```

Pull requests to `master` run the complete transaction and retain the verified
candidate as workflow evidence without publishing it. A successful push to
`master` publishes the exact artifact produced by that transaction.

## Bounded chat-AI authoring

Increment 1 proves one deterministic UTF-8 text packet to one bounded AI
transaction to one validated transactional backend application.

The packet source must already be registered under backend
`content/sources/**`, with the same:

- source ID
- origin content hash
- fragment IDs
- fragment fingerprints

Local private source material belongs under `.private/`. Source packets, tasks,
responses, and previews belong under `.authoring/`. Both directories are
ignored by Git.

Source registration is outside the Increment 1 authoring workflow. The
authoring command does not publish packet-only sources and does not create
backend source objects automatically.

### Ingest a registered source representation

```bash
py scripts/authoring.py ingest \
  --input .private/sources/iam-notes.md \
  --source-id source.personal.iam-notes \
  --source-type own_notes \
  --source-metadata forbidden \
  --title "IAM learning notes" \
  --output .authoring/packets/iam-notes.yaml
```

`--source-metadata` accepts:

```text
forbidden
allowed
```

Its default is `forbidden`. Publication policy is explicit and is not inferred
from `source_type`.

### Prepare the bounded chat task

```bash
py scripts/authoring.py prepare \
  --packet .authoring/packets/iam-notes.yaml \
  --backend ../aws-learning-curve-backend \
  --kinds concept,misconception,question \
  --output .authoring/tasks/iam-notes.md
```

### Preview the repository effect

```bash
py scripts/authoring.py apply \
  --transaction .authoring/responses/iam-notes.yaml \
  --packet .authoring/packets/iam-notes.yaml \
  --backend ../aws-learning-curve-backend \
  --dry-run
```

### Apply the validated transaction

```bash
py scripts/authoring.py apply \
  --transaction .authoring/responses/iam-notes.yaml \
  --packet .authoring/packets/iam-notes.yaml \
  --backend ../aws-learning-curve-backend
```

### Validate using the existing repository authority

```bash
py scripts/validate_content.py
```

`apply` verifies:

- transaction structure
- source-packet hash
- registered backend source identity
- registered source origin content hash
- fragment IDs and fingerprints
- provenance and grounding references
- candidate-only status
- AI transformation metadata
- optimistic concurrency for updates
- derived repository paths
- object schemas
- the complete staged content tree using the existing validator

Multi-file application uses per-file replacement with best-effort rollback on
failure. It is not an atomic filesystem transaction. Validation completes
before repository files are replaced.

The authoring command never commits or publishes.
