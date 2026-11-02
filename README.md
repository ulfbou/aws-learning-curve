# aws-learning-curve

File-based AWS learning content with Python validation, deterministic JSON bundle generation, and automated deployment to GitHub Pages.

## Local verification on Windows 10 Pro with Git Bash

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

## GitHub Pages deployment

The workflow in `.github/workflows/deploy-pages.yml` runs on every push to `master` and can also be started manually. It:

1. installs the Python dependencies;
2. validates the authored YAML content;
3. rebuilds the public JSON bundle and manifest;
4. verifies the complete `public/` artifact and its bundle hash;
5. uploads `public/` and deploys it through GitHub Pages.

In the repository settings, select **Settings > Pages > Build and deployment > Source: GitHub Actions**. The published site is expected at:

```text
https://ulfbou.github.io/aws-learning-curve/
```

The browser uses paths relative to the deployed Pages root, so the project-site prefix is preserved.
