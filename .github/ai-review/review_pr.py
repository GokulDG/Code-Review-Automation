"""Review a pull request with OpenAI and publish the result as a GitHub review.

In GitHub Actions: python review_pr.py
Locally, without touching GitHub: python review_pr.py --dry-run path/to/change.diff
"""
import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Literal

import requests
from openai import OpenAI
from pydantic import BaseModel

COMMENT_PREFIX = "**AI review |"
IGNORED_FILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml"}
IGNORED_DIRS = {"dist", "build", "coverage", "node_modules"}
IGNORED_SUFFIXES = (".md", ".lock", ".map", ".min.js", ".snap", ".svg")
SEVERITY_ORDER = ["critical", "high", "medium", "low"]


class Finding(BaseModel):
    path: str
    line: int
    severity: Literal["critical", "high", "medium", "low"]
    issue: str
    suggestion: str


class Review(BaseModel):
    summary: str
    findings: list[Finding]


@dataclass
class Selection:
    prompt_parts: list[str] = field(default_factory=list)
    added_lines: dict[str, set[int]] = field(default_factory=dict)
    skipped: list[tuple[str, str]] = field(default_factory=list)


def env_int(name, default):
    return int(os.getenv(name) or default)


def is_ignored(path):
    pure = PurePosixPath(path)
    return (
        pure.name in IGNORED_FILES
        or pure.name.endswith(IGNORED_SUFFIXES)
        or bool(IGNORED_DIRS.intersection(pure.parts[:-1]))
    )


def annotate_patch(patch):
    """Prefix patch rows with new-file line numbers and collect the added lines."""
    rows = []
    added = set()
    new_line = None
    for row in patch.splitlines():
        match = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", row)
        if match:
            new_line = int(match.group(1))
            rows.append(row)
        elif new_line is None:
            continue
        elif row.startswith("+"):
            added.add(new_line)
            rows.append(f"{new_line} {row}")
            new_line += 1
        elif row.startswith("-"):
            rows.append(f"- {row}")
        elif row.startswith("\\"):
            continue
        else:
            rows.append(f"{new_line} {row}")
            new_line += 1
    return "\n".join(rows), added


def select_files(files, max_file_chars, max_total_chars):
    """Apply the token controls: drop noise and cap per-file and total diff size."""
    selection = Selection()
    budget = max_total_chars
    for changed in files:
        path = changed["filename"]
        patch = changed.get("patch") or ""
        if changed["status"] == "removed" or is_ignored(path):
            continue
        if not patch:
            selection.skipped.append((path, "no text diff from GitHub"))
            continue
        if len(patch) > max_file_chars:
            selection.skipped.append((path, f"diff over {max_file_chars} characters"))
            continue
        if len(patch) > budget:
            selection.skipped.append((path, "total diff budget used up"))
            continue
        annotated, added = annotate_patch(patch)
        if not added:
            continue
        selection.added_lines[path] = added
        selection.prompt_parts.append(f"FILE: {path}\nPATCH:\n{annotated}")
        budget -= len(patch)
    return selection


def files_from_diff(text):
    """Turn a local unified diff into the same shape as GitHub's PR files API."""
    files = []
    for section in re.split(r"^diff --git ", text, flags=re.M)[1:]:
        target = re.search(r"^\+\+\+ (.+)$", section, flags=re.M)
        source = re.search(r"^--- (.+)$", section, flags=re.M)
        hunk = re.search(r"^@@ ", section, flags=re.M)
        if not (target and source and hunk):
            continue
        removed = target.group(1).strip() == "/dev/null"
        name = source.group(1) if removed else target.group(1)
        files.append({
            "filename": name.strip().removeprefix("a/").removeprefix("b/"),
            "status": "removed" if removed else "modified",
            "patch": section[hunk.start():],
        })
    return files


def no_mentions(text):
    """Stop text derived from the diff from pinging anyone on GitHub."""
    return re.sub(r"@(?=\w)", "@​", text)


def build_review_body(review, selection, existing, max_findings):
    """Split findings into inline comments and the rest, which stay in the summary."""
    findings = sorted(review.findings, key=lambda f: SEVERITY_ORDER.index(f.severity))
    comments = []
    unanchored = []
    repeats = 0
    for finding in findings[:max_findings]:
        issue = no_mentions(finding.issue)
        suggestion = no_mentions(finding.suggestion)
        if finding.line not in selection.added_lines.get(finding.path, set()):
            unanchored.append(
                f"- **{finding.severity}** `{no_mentions(finding.path)}:{finding.line}`: {issue}"
            )
        elif (finding.path, finding.line) in existing:
            repeats += 1
        else:
            comments.append({
                "path": finding.path,
                "line": finding.line,
                "side": "RIGHT",
                "body": f"{COMMENT_PREFIX} {finding.severity}**\n\n{issue}\n\n**Suggested fix:** {suggestion}",
            })

    body = ["## AI Code Review", no_mentions(review.summary)]
    if unanchored:
        body += ["### Findings outside the changed lines", "\n".join(unanchored)]
    if selection.skipped:
        rows = [f"- `{no_mentions(path)}`: {reason}" for path, reason in selection.skipped]
        body += ["### Not reviewed", "\n".join(rows)]
    tail = f"New inline comments: {len(comments)}."
    if repeats:
        tail += f" Already commented: {repeats}."
    if len(findings) > max_findings:
        tail += f" Dropped by the {max_findings} finding cap: {len(findings) - max_findings}."
    body.append(f"{tail} AI findings need human verification.")
    return "\n\n".join(body), comments


def ask_model(prompt):
    system = (Path(__file__).parent / "prompt.md").read_text()
    response = OpenAI(timeout=120, max_retries=2).chat.completions.parse(
        model=os.getenv("OPENAI_MODEL") or "gpt-6-luna",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        response_format=Review,
        max_completion_tokens=env_int("MAX_OUTPUT_TOKENS", 4000),
    )
    message = response.choices[0].message
    if message.parsed is None:
        raise RuntimeError(f"Model returned no review: {message.refusal}")
    if response.usage:
        print(f"Tokens: {response.usage.prompt_tokens} in, {response.usage.completion_tokens} out")
    return message.parsed


class GitHub:
    def __init__(self):
        self.api = os.getenv("GITHUB_API_URL") or "https://api.github.com"
        self.repo = os.environ["GITHUB_REPOSITORY"]
        self.pr = int(os.environ["PR_NUMBER"])
        self.headers = {
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _request(self, method, path, **kwargs):
        url = f"{self.api}/repos/{self.repo}/pulls/{self.pr}{path}"
        response = requests.request(method, url, headers=self.headers, timeout=40, **kwargs)
        if not response.ok:
            raise RuntimeError(f"GitHub {method} {path} failed: {response.status_code} {response.text[:500]}")
        return response.json()

    def _paginate(self, path):
        rows = []
        for page in range(1, 31):
            batch = self._request("GET", path, params={"per_page": 100, "page": page})
            rows.extend(batch)
            if len(batch) < 100:
                break
        return rows

    def files(self):
        return self._paginate("/files")

    def existing_comment_locations(self):
        return {
            (comment["path"], comment["line"])
            for comment in self._paginate("/comments")
            if comment["body"].startswith(COMMENT_PREFIX)
        }

    def publish(self, body, comments):
        payload = {
            "commit_id": os.environ["PR_HEAD_SHA"],
            "event": "COMMENT",
            "body": body,
            "comments": comments,
        }
        self._request("POST", "/reviews", json=payload)


def run(files, github=None):
    selection = select_files(
        files,
        env_int("MAX_FILE_DIFF_CHARS", 12000),
        env_int("MAX_DIFF_CHARS", 30000),
    )
    prompt = "\n\n".join(selection.prompt_parts)
    print(f"Reviewing {len(selection.prompt_parts)} of {len(files)} files, "
          f"about {len(prompt) // 4} input tokens")
    for path, reason in selection.skipped:
        print(f"Skipped {path}: {reason}")

    if github is None:
        print(f"\n--- Prompt sent to the model ---\n{prompt}\n--- End of prompt ---\n")
        if not os.getenv("OPENAI_API_KEY"):
            print("OPENAI_API_KEY is not set, so the model call was skipped.")
            return

    if not prompt:
        if selection.skipped and github:
            github.publish("## AI Code Review\n\nNothing was reviewed. " + "\n".join(
                f"\n- `{no_mentions(path)}`: {reason}" for path, reason in selection.skipped
            ), [])
        print("No eligible changed lines to review")
        return

    review = ask_model(prompt)
    existing = github.existing_comment_locations() if github else set()
    body, comments = build_review_body(review, selection, existing, env_int("MAX_FINDINGS", 8))
    if github is None:
        print(json.dumps({"body": body, "comments": comments}, indent=2))
        return
    github.publish(body, comments)
    print(f"Published review with {len(comments)} inline comments")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", metavar="DIFF_FILE", help="review a local diff and print the result")
    args = parser.parse_args()
    if args.dry_run:
        run(files_from_diff(Path(args.dry_run).read_text()))
        return
    github = GitHub()
    run(github.files(), github)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"AI PR review failed: {exc}", file=sys.stderr)
        raise
