# aws-learning-curve

Frontend and tooling for AWS Learning Curve. Authored learning content is stored separately on the orphan `backend` branch under `content/**`.

## Ownership

- `master` owns the frontend, schemas, Python tooling, and CI/CD policy.
- `backend` owns only `content/**`.
- `public/data/**` is generated during each release transaction and is never committed.

## Transactional release

`scripts/release.py` is the shared local and CI release entry point. It combines one frontend commit with one backend commit in an isolated workspace, validates the content, generates the public data, builds the frontend, verifies the complete Pages artifact, and promotes the artifact only after every step succeeds.

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

Pull requests to `master` run the complete transaction and retain the verified candidate as workflow evidence without publishing it. A successful push to `master` publishes the exact artifact produced by that transaction.
