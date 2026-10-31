"""Run with: python -m unittest discover -s .github/ai-review/tests"""
import json
import os
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import review_pr  # noqa: E402

PATCH = """@@ -10,3 +10,4 @@ function total() {
 const a = 1;
-const b = 2;
+const b = 3;
+const c = 4;
 return a;
\\ No newline at end of file"""


def finding(path="src/a.js", line=11, severity="high", issue="Bug", suggestion="Fix"):
    return review_pr.Finding(path=path, line=line, severity=severity, issue=issue, suggestion=suggestion)


class AnnotatePatch(unittest.TestCase):
    def test_numbers_new_side_and_collects_added_lines(self):
        annotated, added = review_pr.annotate_patch(PATCH)
        self.assertEqual(added, {11, 12})
        self.assertIn("11 +const b = 3;", annotated)
        self.assertIn("12 +const c = 4;", annotated)
        self.assertIn("13  return a;", annotated)
        self.assertIn("- -const b = 2;", annotated)


class SelectFiles(unittest.TestCase):
    def file(self, name, patch=PATCH, status="modified"):
        return {"filename": name, "status": status, "patch": patch}

    def test_ignores_noise(self):
        names = ["package-lock.json", "sub/yarn.lock", "dist/index.js", "web/build/a.js",
                 "README.md", "src/x.min.js", "src/__snapshots__/a.snap"]
        selection = review_pr.select_files([self.file(n) for n in names], 1000, 1000)
        self.assertEqual(selection.prompt_parts, [])
        self.assertEqual(selection.skipped, [])

    def test_skips_removed_files(self):
        selection = review_pr.select_files([self.file("src/a.js", status="removed")], 1000, 1000)
        self.assertEqual(selection.added_lines, {})

    def test_reports_binary_and_oversized_files(self):
        files = [self.file("logo.png", patch=None), self.file("src/big.js", patch=PATCH * 5)]
        selection = review_pr.select_files(files, len(PATCH) + 1, 1000)
        self.assertEqual([path for path, _ in selection.skipped], ["logo.png", "src/big.js"])

    def test_stops_at_total_budget_and_says_so(self):
        files = [self.file("src/a.js"), self.file("src/b.js")]
        selection = review_pr.select_files(files, 1000, len(PATCH) + 1)
        self.assertEqual(list(selection.added_lines), ["src/a.js"])
        self.assertEqual(selection.skipped, [("src/b.js", "total diff budget used up")])


class FilesFromDiff(unittest.TestCase):
    def test_parses_changed_and_deleted_files(self):
        diff = (
            "diff --git a/src/a.js b/src/a.js\n--- a/src/a.js\n+++ b/src/a.js\n" + PATCH + "\n"
            "diff --git a/old.js b/old.js\ndeleted file mode 100644\n--- a/old.js\n+++ /dev/null\n"
            "@@ -1 +0,0 @@\n-gone\n"
        )
        files = review_pr.files_from_diff(diff)
        self.assertEqual([(f["filename"], f["status"]) for f in files],
                         [("src/a.js", "modified"), ("old.js", "removed")])


class BuildReview(unittest.TestCase):
    def selection(self):
        return review_pr.Selection(added_lines={"src/a.js": {11, 12}})

    def build(self, findings, existing=frozenset(), max_findings=8):
        review = review_pr.Review(summary="Summary", findings=findings)
        return review_pr.build_review_body(review, self.selection(), existing, max_findings)

    def test_inline_comment_on_added_line(self):
        _, comments = self.build([finding()])
        self.assertEqual(comments[0]["path"], "src/a.js")
        self.assertEqual(comments[0]["line"], 11)
        self.assertEqual(comments[0]["side"], "RIGHT")

    def test_finding_off_the_diff_moves_to_summary(self):
        body, comments = self.build([finding(line=99)])
        self.assertEqual(comments, [])
        self.assertIn("`src/a.js:99`", body)

    def test_skips_lines_already_commented(self):
        body, comments = self.build([finding()], existing={("src/a.js", 11)})
        self.assertEqual(comments, [])
        self.assertIn("Already commented: 1", body)

    def test_cap_keeps_most_severe(self):
        body, comments = self.build([finding(severity="low"), finding(line=12, severity="critical")], max_findings=1)
        self.assertEqual(comments[0]["line"], 12)
        self.assertIn("Dropped by the 1 finding cap: 1", body)

    def test_neutralises_mentions(self):
        _, comments = self.build([finding(issue="ping @octocat")])
        self.assertNotIn("@octocat", comments[0]["body"])


class Mock(BaseHTTPRequestHandler):
    """Stands in for both api.github.com and api.openai.com."""
    posted = []
    openai_requests = []
    files = []
    comments = []
    findings = []

    def log_message(self, *args):
        pass

    def reply(self, data):
        raw = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        page = int(self.path.split("page=")[-1]) if "page=" in self.path else 1
        rows = self.files if "/files" in self.path else self.comments
        self.reply(rows if page == 1 else [])

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path.endswith("/reviews"):
            type(self).posted.append({"auth": self.headers["Authorization"], **body})
            return self.reply({"id": 1})
        type(self).openai_requests.append(body)
        content = json.dumps({"summary": "Two problems.", "findings": self.findings})
        self.reply({
            "id": "chatcmpl-1", "object": "chat.completion", "created": 1, "model": body["model"],
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": content, "refusal": None}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
        })


class EndToEnd(unittest.TestCase):
    """Runs the real script and OpenAI SDK against a local HTTP mock."""

    def setUp(self):
        Mock.posted, Mock.openai_requests = [], []
        Mock.files = [{"filename": "src/a.js", "status": "modified", "patch": PATCH},
                      {"filename": "package-lock.json", "status": "modified", "patch": PATCH}]
        Mock.comments = [{"path": "src/a.js", "line": 12, "body": "**AI review | low**\n\nOld"}]
        Mock.findings = [
            {"path": "src/a.js", "line": 11, "severity": "high", "issue": "Bug", "suggestion": "Fix"},
            {"path": "src/a.js", "line": 12, "severity": "low", "issue": "Repeat", "suggestion": "Fix"},
            {"path": "src/a.js", "line": 90, "severity": "medium", "issue": "Elsewhere", "suggestion": "Fix"},
        ]
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Mock)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def run_script(self):
        url = f"http://127.0.0.1:{self.server.server_port}"
        env = {
            **os.environ, "GITHUB_API_URL": url, "OPENAI_BASE_URL": f"{url}/v1",
            "OPENAI_API_KEY": "test-key", "GITHUB_TOKEN": "test-token", "OPENAI_MODEL": "test-model",
            "GITHUB_REPOSITORY": "me/repo", "PR_NUMBER": "7", "PR_HEAD_SHA": "abc123",
        }
        return subprocess.run([sys.executable, str(ROOT / "review_pr.py")], env=env,
                              capture_output=True, text=True, timeout=60)

    def test_publishes_a_comment_review(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)

        review = Mock.posted[0]
        self.assertEqual(review["auth"], "Bearer test-token")
        self.assertEqual(review["event"], "COMMENT")
        self.assertEqual(review["commit_id"], "abc123")
        self.assertEqual([(c["path"], c["line"]) for c in review["comments"]], [("src/a.js", 11)])
        self.assertIn("src/a.js:90", review["body"])

        request = Mock.openai_requests[0]
        self.assertEqual(request["model"], "test-model")
        self.assertEqual(request["max_completion_tokens"], 4000)
        self.assertEqual(request["response_format"]["type"], "json_schema")
        prompt = request["messages"][1]["content"]
        self.assertIn("FILE: src/a.js", prompt)
        self.assertNotIn("package-lock.json", prompt)

    def test_makes_no_paid_call_when_only_noise_changed(self):
        Mock.files = Mock.files[1:]
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Mock.openai_requests, [])
        self.assertEqual(Mock.posted, [])

    def test_tells_the_pr_when_everything_was_too_large(self):
        Mock.files = [{"filename": "src/big.js", "status": "modified", "patch": "x" * 13000}]
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Mock.openai_requests, [])
        self.assertIn("src/big.js", Mock.posted[0]["body"])


if __name__ == "__main__":
    unittest.main()
