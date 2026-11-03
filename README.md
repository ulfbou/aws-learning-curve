# AWS Learning Curve

AWS Learning Curve is a learner-centered system for building, practising, and retaining usable AWS mental models.

The repository serves one learner who wants to:

- understand AWS services and how they fit together;
- remember important distinctions;
- identify and correct misconceptions;
- practise recall and application;
- reason about cloud architectures;
- connect course material, personal notes, experiments, and AI-assisted synthesis;
- develop practical AWS and system-design competence over time.

The primary optimization target is learning effectiveness:

```text
understanding
recall
retention
application
transfer
architectural reasoning
```

The repository is not primarily a publication, governance, compliance, evidence-management, or content-management platform.

## Product model

The main learning loop is:

```text
learning need
    ->
bounded learning context
    ->
AI-assisted learning response
    ->
candidate learning-artifact transaction
    ->
deterministic validation
    ->
learner review
    ->
accepted repository change
    ->
study or practice
    ->
explicit unresolved point
```

The repository does not attempt to automate this entire loop at once. Development proceeds through small, usable increments.

## Learning objects

The existing object kinds represent learning tools:

- `concept` — a mental model, distinction, process, principle, or mechanism;
- `misconception` — a learning trap and its correction;
- `question` — a recall, explanation, diagnosis, or reflection activity;
- `scenario` — an application and reasoning activity;
- `procedure` — a repeatable decision or troubleshooting process;
- `competency` — an observable learning objective;
- `learning_unit` — a structured learning sequence;
- `source` — registered learning input;
- `generation_run` — a record of a generation operation.

Existing kinds should be reused before new kinds are introduced.

For example:

- a comparison can be represented as a contrast concept;
- a practice set can be a selected group of questions and scenarios;
- a study guide can be a generated view over existing objects;
- a concept map can be derived from existing relationships.

A new object kind is justified only when repeated use reveals a concrete modeling gap.

## Important state boundaries

The repository distinguishes four kinds of information.

### Learning content

Durable learning objects such as concepts, questions, scenarios, misconceptions, procedures, competencies, and learning units.

### Learner state

Private observations such as:

- attempts;
- confidence;
- remaining uncertainty;
- review history;
- forgotten concepts;
- current study priorities.

Learner state must not enter public release artifacts.

### Source material

Learning inputs such as:

- personal notes;
- course notes;
- classroom material;
- video transcriptions;
- AWS documentation;
- labs and experiments.

Source references help recover context, revisit an explanation, and support safe synthesis. They do not define the product mission.

### Generated release artifacts

Derived browser data and static assets produced for GitHub Pages.

Generated files are outputs, not canonical authored content.

## Repository status is not learner mastery

Repository object status and learner understanding are separate.

For example:

- `candidate` means that a repository object awaits review;
- `published` means that an object is accepted for use in the repository;
- a learner may understand a candidate explanation;
- a learner may still misunderstand a published concept.

Publication does not imply mastery.

Likewise, AI may propose that a response indicates a misconception, but it cannot independently declare that the learner understands a concept, has corrected a misconception, or has achieved a competency.

## Human, AI, and Python responsibilities

### Learner

The learner:

- states learning needs;
- reviews AI-generated candidates;
- decides whether an artifact is useful;
- approves repository changes;
- records what remains unclear;
- determines the next learning need.

### AI collaborator

AI may:

- explain;
- compare;
- reorganize;
- connect concepts;
- generate questions and scenarios;
- surface possible misconceptions;
- propose improvements to learning objects;
- return machine-readable candidate transactions.

AI does not:

- choose repository paths;
- assign system-managed revisions, hashes, or timestamps;
- mutate the repository directly;
- publish its own output;
- infer mastery as an authoritative fact;
- decide that a learning artifact was effective without learner interaction.

### Deterministic Python tooling

Python owns:

- parsing and normalization;
- repository loading;
- bounded context selection;
- schema and repository validation;
- path derivation;
- revision and content-hash checks;
- generation-run identifiers;
- dry-run previews;
- repository mutation;
- release construction and verification.

These mechanisms make learning work reliable. They are supporting infrastructure, not the product purpose.

## Canonical and generated data

The repository preserves these architectural boundaries:

```text
YAML
    ->
canonical authored repository content

JSON
    ->
generated browser data

public/
    ->
generated and static GitHub Pages artifact

private learner state
    ->
excluded from public release artifacts
```

## Repository ownership for bounded learning

The bounded workflow preserves two explicit roots:

- the frontend checkout is the tooling root and owns `scripts/`, `schemas/`,
  tests, and CI/CD policy;
- the backend worktree is the content workspace and owns canonical
  `content/**`.

The tooling root is derived from `scripts/content_workflow.py`. The backend
worktree is supplied through `--content-workspace`.

The workflow boundary is:

```text
query
  -> candidate transaction
  -> immutable prepared plan
  -> dry-run prepared plan
  -> execute the same prepared plan
```

Dry-run and execution must therefore use the same prepared timestamp, content
hashes, paths, and serialized output.

## Current development direction

The next runtime increment is intentionally narrow:

```text
learning need
    ->
deterministic bounded query
    ->
learning context
    ->
AI candidate transaction
    ->
Python dry-run
    ->
human-reviewed apply
    ->
structured operation result
    ->
short study use
    ->
explicit unresolved point
```

The first intended scenario is:

```text
Understand the difference between IAM users, roles, and policies.
```

Initially justified retrieval methods are limited to:

- exact semantic ID;
- alias;
- keyword;
- tag;
- object kind;
- content status;
- direct relationships.

The current direction does not commit to embeddings, semantic similarity, graph infrastructure, adaptive learning, automatic mastery judgments, automatic study planning, or unattended AI changes.

## Local verification

The frontend checkout does not contain canonical authored content. Local
release verification therefore requires both worktrees:

```text
aws-learning-curve-frontend/
    frontend code, schemas, tooling, tests, and CI/CD policy

aws-learning-curve-backend/
    canonical content/**
```

Install frontend dependencies from the frontend worktree:

```bash
py -m pip install --requirement requirements.txt
npm ci
```

Run the bounded-workflow tests:

```bash
py -X utf8 -m unittest -v \
  tests.test_learning_workflow_conflicts \
  tests.test_learning_workflow_e2e
```

Run the same verified release transaction used by CI:

```bash
py -X utf8 scripts/release.py \
  --backend ../aws-learning-curve-backend
```

The release command combines the frontend and backend worktrees in an isolated
workspace, validates canonical content, generates browser data, builds the
frontend, verifies the complete Pages artifact, and promotes the result only
after every step succeeds.

For explicit CI-style paths and output:

```bash
py -X utf8 scripts/release.py \
  --ci \
  --frontend . \
  --backend ../aws-learning-curve-backend \
  --output .dx/release
```

Do not run `validate_content.py` or `build_learning_bundle.py` against the
frontend checkout alone. Those tools require canonical backend content and are
orchestrated through `release.py`.

### Operational release boundary

Do not run `validate_content.py` or `build_learning_bundle.py` against the
frontend checkout alone. Those tools require canonical content from the
backend worktree and are orchestrated through `scripts/release.py`.

Use:

```bash
py -X utf8 scripts/release.py \
  --backend ../aws-learning-curve-backend
```

The release transaction combines the frontend tooling root with the backend
content workspace before validation, bundle generation, frontend build, and
artifact verification.

## GitHub Pages deployment

The GitHub Pages workflow checks out both repository roots:

```text
master
    -> frontend code, schemas, tooling, tests, and CI/CD policy

backend
    -> canonical content/**
```

It then invokes the same transactional release implemented by
`scripts/release.py`.

The transaction:

1. identifies the exact frontend and backend revisions;
2. assembles both roots in an isolated workspace;
3. validates canonical backend content with frontend-owned schemas and tooling;
4. generates public browser data;
5. builds frontend assets;
6. verifies the complete Pages artifact;
7. records the release manifest;
8. promotes the artifact only after every step succeeds.

Pull requests run the complete transaction and retain the verified candidate as
workflow evidence without publishing it. A successful push to `master`
publishes the exact artifact produced by the verified transaction.

Generated `public/data/**` remains release output. It is not canonical authored
content and must not replace the backend ownership boundary.

In repository settings, GitHub Pages uses GitHub Actions as the deployment
source.

## Explicit non-goals

The current architecture does not commit to:

- a knowledge-graph platform;
- a graph database;
- embeddings;
- semantic similarity search;
- automatic learning paths;
- automatic mastery decisions;
- autonomous study planning;
- unattended AI repository mutation;
- automatic publication;
- a generalized multi-user learning platform;
- a new artifact kind for every learning activity.

The governing development rule is:

> Build one bounded learning interaction, use it in a real AWS study session, and let the observed learning need determine the next increment.
