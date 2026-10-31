# React sample with an automated AI code reviewer

A small React shop app plus a GitHub Actions workflow. When a pull request is opened or updated, a Python script sends the diff to the OpenAI API and posts the findings on the PR as inline comments and a summary.

This follows **Scenario 2** of the Dev Knot video [ChatGPT + GitHub: AI Code Review & Auto PR Comments](https://www.youtube.com/watch?v=6UyxMQdLvJA). The video description names it "Build an automated AI Code Reviewer using GitHub Actions", with Python, the OpenAI API and the GitHub REST API. The code is modelled on the author's [reference repo](https://github.com/pradeepmangadu/devknot-automated-pr-review). The scenario was confirmed from the description and that repo, because the video transcript could not be downloaded.

## What's here

| Path | Purpose |
| --- | --- |
| `src/` | The React app and its tests |
| `.github/workflows/ai-review.yml` | The review workflow |
| `.github/ai-review/review_pr.py` | Filters the diff, calls OpenAI, posts the GitHub review |
| `.github/ai-review/prompt.md` | Reviewer instructions, safe to edit |
| `.github/ai-review/tests/` | Unit tests and a mocked end-to-end test |
| `demo/flawed-change.patch` | Intentionally buggy change for a test PR |

## Run the app

Tested on Node 22.1. Vite stays on version 6 because Vite 8 needs Node 22.12 or later.

```bash
npm ci
```

```bash
npm test
```

```bash
npm run build
```

```bash
npm run dev
```

If `npm install` crashes with `Cannot read properties of null (reading 'edgesOut')`, that is a bug in npm 10.7. `npm ci` works, or run `npx npm@11 install` when you need to change dependencies.

## GitHub setup

Do these steps in order. Step 1 must land on `main` before the test PR, because the workflow runs the review script from the base branch.

### 1. Create the repository and push `main`

`react-sample` must be the **repository root**. GitHub only reads `.github/workflows` at the root, so nothing will run if you push the parent folder instead.

Create an empty repository on GitHub with no README or license, then run these from `react-sample/`, replacing `YOUR_USER/YOUR_REPO`:

```bash
git init -b main
```

```bash
git add .
```

```bash
git commit -m "Initial commit"
```

```bash
git remote add origin https://github.com/YOUR_USER/YOUR_REPO.git
```

```bash
git push -u origin main
```

### 2. Add the API key

1. Create a key at [platform.openai.com/api-keys](https://platform.openai.com/api-keys). API usage is billed separately from a ChatGPT subscription, so the API account needs credit.
2. In the repository, open **Settings > Secrets and variables > Actions > Secrets**.
3. Add a repository secret named `OPENAI_API_KEY`.

Never put the key in a file. The `GITHUB_TOKEN` is provided automatically, so you don't need to add it.

### 3. Check workflow permissions

The workflow requests only `contents: read` and `pull-requests: write`, so the default repository settings should work. If the run fails with `403 Resource not accessible by integration`, open **Settings > Actions > General > Workflow permissions** and select **Read and write permissions**. Organization repositories may also need an admin to allow this.

### 4. Choose a model (optional)

The default is `gpt-6-luna`, the model used in the author's repo and listed at $0.10 input and $0.50 output per 1M tokens on 2026-10-31. To use another model, add a variable named `OPENAI_MODEL` under **Settings > Secrets and variables > Actions > Variables**. It must support Structured Outputs.

### 5. Open a test PR

```bash
git switch -c demo/review-bugs
```

```bash
git apply demo/flawed-change.patch
```

```bash
git commit -am "Demo: add coupon lookup"
```

```bash
git push -u origin demo/review-bugs
```

Then open a PR into `main`. The **AI PR Review** check should finish in about a minute, and `github-actions[bot]` should post a summary and inline comments. Don't merge this PR. The patch contains a fake key, an XSS hole, missing null handling and a `NaN` discount for unknown coupons.

To confirm the other triggers, push another commit, which should repeat the review without duplicating comments on the same lines. A draft PR should show the job as skipped.

## How it behaves

**Token controls**

- Draft PRs are skipped, and marking one ready for review starts the review.
- Lockfiles, Markdown, build output, source maps, snapshots and minified files are not sent.
- A file's diff is capped at 12,000 characters, the whole PR at 30,000, and the model output at 4,000 tokens. Each run costs about $0.003 at most with the default model.
- Anything skipped for size is listed under **Not reviewed** on the PR.
- A newer push cancels the run in progress, and at most 8 findings are posted, most severe first.

To change a limit, add `MAX_DIFF_CHARS`, `MAX_FILE_DIFF_CHARS`, `MAX_OUTPUT_TOKENS` or `MAX_FINDINGS` to the `env` block of the workflow's review step.

**Safety**

- The workflow uses `pull_request`, never `pull_request_target`.
- PRs from forks and Dependabot are skipped. They don't receive secrets, and this stops strangers spending your API credit.
- The review code is checked out from the base commit and PR code is never run, so a PR can't alter the script that holds the key. As a result, edits to `review_pr.py` or `prompt.md` take effect only after they merge.
- Actions are pinned to full commit SHAs, and Python packages to exact versions.
- The bot posts with the `COMMENT` event, so it can't approve or block a PR.
- Comments are only anchored on lines the PR added. Findings elsewhere stay in the summary.
- Diffs are treated as untrusted input, and `@` mentions in model output are neutralised so a crafted diff can't make the bot ping people.

**Limits to know about**

- Diffs are sent to OpenAI, including any secrets committed in them. Check that fits your data policy before using this on private code.
- The model sees only the diff, not the rest of the codebase, so it will miss problems that need wider context.
- Each push re-reviews the whole PR diff, so costs repeat, and a finding can reappear if its line moves.
- AI review adds to human review and doesn't replace it.

## Test the reviewer locally

These commands need Python 3.10 or later and no API key. Run the unit and mocked end-to-end tests:

```bash
python3 -m venv .venv && .venv/bin/pip install -r .github/ai-review/requirements.txt
```

```bash
.venv/bin/python -m unittest discover -s .github/ai-review/tests
```

Dry-run a diff to see the filtering and the exact prompt. Nothing is posted to GitHub. If `OPENAI_API_KEY` is set in your shell, this does call OpenAI and prints the review it would post.

```bash
.venv/bin/python .github/ai-review/review_pr.py --dry-run demo/flawed-change.patch
```
