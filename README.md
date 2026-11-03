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

- `concept` â€” a mental model, distinction, process, principle, or mechanism;
- `misconception` â€” a learning trap and its correction;
- `question` â€” a recall, explanation, diagnosis, or reflection activity;
- `scenario` â€” an application and reasoning activity;
- `procedure` â€” a repeatable decision or troubleshooting process;
- `competency` â€” an observable learning objective;
- `learning_unit` â€” a structured learning sequence;
- `source` â€” registered learning input;
- `generation_run` â€” a record of a generation operation.

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

The normal environment is Windows 10 Pro with Git Bash and native Windows Python.

```bash
py -m pip install --requirement requirements.txt
npm ci
py scripts/validate_content.py
py scripts/build_learning_bundle.py
npm run build:css
node --check public/app.js
py scripts/verify_pages.py
py -m http.server 8000 --directory public
```

Then open:

```text
http://localhost:8000/
```

## GitHub Pages deployment

The workflow in `.github/workflows/deploy-pages.yml` runs on every push to `master` and may also be started manually.

It:

1. checks out the repository;
2. installs Python dependencies;
3. installs frontend dependencies;
4. validates authored YAML content;
5. builds the public JSON bundle and bundle manifest;
6. builds production CSS;
7. checks browser JavaScript syntax;
8. verifies the complete `public/` artifact;
9. uploads and deploys the GitHub Pages artifact.

In repository settings, select:

```text
Settings
    ->
Pages
    ->
Build and deployment
    ->
Source: GitHub Actions
```

The expected project site is:

```text
https://ulfbou.github.io/aws-learning-curve/
```

Browser asset and data paths remain relative to the deployed Pages root.

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
