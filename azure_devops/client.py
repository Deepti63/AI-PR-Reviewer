# azure_devops/client.py
# ─────────────────────────────────────────────────────────────
# PURPOSE: All communication with Azure DevOps REST API.
# Fetch PR details, diffs, and post review comments.
# ─────────────────────────────────────────────────────────────

import difflib
import base64
import requests
from typing import List, Optional
from config import AzureDevOpsConfig
from azure_devops.models import PullRequest, PRFile, WebhookComment


class AzureDevOpsClient:
    """
    Client for the Azure DevOps REST API.

    Azure DevOps uses Basic Auth with a PAT token.
    The format is: base64(":PAT_TOKEN") — note the colon prefix.

    Example:
        PAT = "mytoken123"
        encoded = base64(":mytoken123") = "Om15dG9rZW4xMjM="
        Header = "Authorization: Basic Om15dG9rZW4xMjM="
    """

    def __init__(self, config: AzureDevOpsConfig):
        self.config = config

        # Build Basic Auth header using base64 encoded PAT
        credentials = f":{config.pat}"
        encoded = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")

        self.headers = {
            "Authorization": f"Basic {encoded}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        # Base URL: https://dev.azure.com/{org}/{project}/_apis
        self.base_url = f"{config.org_url}/{config.project}/_apis"

        # Git API base — for repo-specific calls
        self.git_url = f"{self.base_url}/git/repositories/{config.repo}"

    def _make_request(
        self,
        method: str,
        url: str,
        payload: Optional[dict] = None
    ) -> dict:
        """
        Central HTTP request handler.
        All HTTP calls go through here — one place for
        error handling, timeouts, and response parsing.
        """
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=self.headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()

            # Some responses have no body (204 No Content)
            # response.json() would crash on empty body
            if response.content:
                return response.json()
            return {}

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code
            if status == 401:
                raise ValueError(
                    "❌ Azure DevOps PAT is invalid or expired.\n"
                    "   Generate a new one at: "
                    "https://dev.azure.com/deeptisimba/_usersSettings/tokens"
                ) from e
            elif status == 404:
                raise ValueError(
                    f"❌ Resource not found.\n"
                    f"   Check project name, repo name, and PR number.\n"
                    f"   URL attempted: {url}"
                ) from e
            else:
                raise ValueError(
                    f"❌ Azure DevOps API error {status}:\n"
                    f"   {e.response.text}"
                ) from e

        except requests.exceptions.ConnectionError:
            raise ConnectionError(
                "❌ Cannot reach Azure DevOps.\n"
                "   Check your network or org URL."
            )

        except requests.exceptions.Timeout:
            raise TimeoutError("❌ Azure DevOps API timed out after 30s.")

    def get_pull_request(self, pr_id: int) -> PullRequest:
        """
        Fetches PR metadata and all changed files with diffs.
        """
        print(f"🔍 Fetching PR #{pr_id}...")

        url = f"{self.git_url}/pullrequests/{pr_id}?api-version=7.1"
        data = self._make_request("GET", url)

        files = self._get_pr_files(pr_id)

        return PullRequest(
            id=data["pullRequestId"],
            title=data["title"],
            description=data.get("description") or "",
            author=data["createdBy"]["displayName"],
            source_branch=data["sourceRefName"].replace("refs/heads/", ""),
            target_branch=data["targetRefName"].replace("refs/heads/", ""),
            files=files
        )

    def _get_pr_files(self, pr_id: int) -> List[PRFile]:
        """
        Fetches changed files and their diffs for a PR.

        Azure DevOps diff flow:
        Step 1: Get iterations (each push to PR = one iteration)
        Step 2: Get changed files in the latest iteration
        Step 3: For each file, fetch before + after and build diff
        """
        # Step 1: Get iterations
        iter_url = (
            f"{self.git_url}/pullrequests/{pr_id}"
            f"/iterations?api-version=7.1"
        )
        iterations = self._make_request("GET", iter_url)

        if not iterations.get("value"):
            print("⚠️  No iterations found for this PR")
            return []

        # 🧠 CONCEPT: max() with lambda
        # lambda x: x["id"] is a tiny anonymous function
        # max() uses it to find the iteration with the highest id
        latest_iteration = max(
            iterations["value"],
            key=lambda x: x["id"]
        )
        iteration_id = latest_iteration["id"]

        # Step 2: Get changed files in this iteration
        changes_url = (
            f"{self.git_url}/pullrequests/{pr_id}"
            f"/iterations/{iteration_id}/changes?api-version=7.1"
        )
        changes_data = self._make_request("GET", changes_url)

        # Step 3: Build PRFile objects with diffs
        files = []
        for change in changes_data.get("changeEntries", []):
            item = change.get("item", {})
            filename = item.get("path", "")

            # Skip folders — we only want files
            if item.get("isFolder", False):
                continue

            change_type = change.get("changeType", "edit")

            # Fetch the diff for this file
            diff = self._get_file_diff(pr_id, iteration_id, filename)

            files.append(PRFile(
                filename=filename,
                change_type=change_type,
                diff=diff
            ))

        print(f"   Found {len(files)} changed files")
        return files

    def _get_file_diff(
        self,
        pr_id: int,
        iteration_id: int,
        filename: str
    ) -> Optional[str]:
        """
        Fetches ONLY the changed lines for a file.

        Strategy:
        1. Fetch file content BEFORE the PR (target branch)
        2. Fetch file content AFTER the PR (source branch)
        3. Use difflib to compare and show only changes + context

        🧠 CONCEPT: Best-effort fetching
        If this fails for one file we catch the exception and
        return None so the review continues with other files.
        Never let one file crash the whole review.
        """
        try:
            # File as it was BEFORE this PR (target/master)
            original = self._fetch_file_at_commit(
                filename,
                is_target=True,
                pr_id=pr_id
            )

            # File as it is AFTER this PR (source/feature branch)
            modified = self._fetch_file_at_commit(
                filename,
                is_target=False,
                pr_id=pr_id
            )

            if original is None and modified is None:
                return f"[Could not retrieve content for {filename}]"

            # Build diff using configured context lines
            return self._build_diff(
                filename,
                original or "",
                modified or "",
                context_lines=self.config.diff_context_lines
            )

        except Exception as e:
            print(f"   ⚠️  Could not fetch diff for {filename}: {e}")
            return None

    def _fetch_file_at_commit(
        self,
        filename: str,
        is_target: bool,
        pr_id: int
    ) -> Optional[str]:
        """
        Fetches raw file content at either end of a PR.

        🧠 CONCEPT: is_target flag
        True  = target branch = master = file BEFORE the PR
        False = source branch = feature = file AFTER the PR
        Comparing before vs after gives us the real diff.

        🧠 CONCEPT: dict unpacking with **
        {**self.headers, "Accept": "text/plain"} creates a NEW dict
        copying all of self.headers then overriding just Accept.
        This avoids modifying self.headers for other requests.
        """
        try:
            pr_url = f"{self.git_url}/pullrequests/{pr_id}?api-version=7.1"
            pr_data = self._make_request("GET", pr_url)

            if is_target:
                # Before: what exists on master/main right now
                commit_id = pr_data.get(
                    "lastMergeTargetCommit", {}
                ).get("commitId")
            else:
                # After: what the PR proposes to merge in
                commit_id = pr_data.get(
                    "lastMergeSourceCommit", {}
                ).get("commitId")

            if not commit_id:
                return None

            content_url = (
                f"{self.git_url}/items"
                f"?path={filename}"
                f"&version={commit_id}"
                f"&versionType=commit"
                f"&api-version=7.1"
            )

            raw_headers = {**self.headers, "Accept": "text/plain"}
            response = requests.get(
                content_url,
                headers=raw_headers,
                timeout=30
            )

            if response.status_code == 200:
                return response.text
            elif response.status_code == 404:
                # New file added in PR — did not exist before
                return None

            return None

        except Exception:
            return None

    def _build_diff(
        self,
        filename: str,
        original: str,
        modified: str,
        context_lines: int = 3
    ) -> str:
        """
        Builds a unified diff between original and modified content.

        🧠 CONCEPT: difflib.unified_diff
        Python built-in module — no install needed.
        Produces standard git-style diff output.

        🧠 CONCEPT: context_lines (the n= parameter)
        Controls how many UNCHANGED lines appear around each change.

        context_lines=0 (diff only):     context_lines=3 (default):
        ────────────────────────         ──────────────────────────
        @@ -4,0 +5 @@                    @@ -2,4 +2,5 @@
        +gem 'rake'                       gem 'rspec-core'
                                          gem 'rspec-expectations'
                                          gem 'rake'
                                         +gem 'rake'

        🧠 CONCEPT: Ternary expression
        value_if_true if condition else value_if_false
        Same as a 2-line if/else but on one line.
        """
        original_lines = original.splitlines(keepends=True)
        modified_lines = modified.splitlines(keepends=True)

        diff_lines = list(difflib.unified_diff(
            original_lines,
            modified_lines,
            fromfile=f"before/{filename}",
            tofile=f"after/{filename}",
            n=context_lines,
            #lineterm=""
        ))

        if not diff_lines:
            return "[No changes detected in file content]"

        # Label so the AI knows what context mode was used
        context_label = (
            "diff only — no context lines"
            if context_lines == 0
            else f"{context_lines} lines of context per change"
        )

        return f"[{context_label}]\n" + "".join(diff_lines)

    def post_pr_comment(
        self,
        pr_id: int,
        review_text: str,
        thread_id: Optional[int] = None
    ) -> bool:
        """
        Posts a review comment to a PR thread.

        Two modes:
        thread_id=None → creates a NEW thread on the PR
        thread_id=123  → replies to an EXISTING thread
                         (used when replying to @ai-reviewer comment)
        """
        formatted = self._format_review(review_text)

        if thread_id:
            url = (
                f"{self.git_url}/pullrequests/{pr_id}"
                f"/threads/{thread_id}/comments?api-version=7.1"
            )
            payload = {"content": formatted}
        else:
            url = (
                f"{self.git_url}/pullrequests/{pr_id}"
                f"/threads?api-version=7.1"
            )
            payload = {
                "comments": [{
                    "parentCommentId": 0,
                    "content": formatted,
                    "commentType": 1
                }],
                "status": "active"
            }

        try:
            self._make_request("POST", url, payload)
            print(f"✅ Review posted to PR #{pr_id}")
            return True
        except Exception as e:
            print(f"❌ Failed to post review: {e}")
            return False

    def _format_review(self, review_text: str) -> str:
        """
        Wraps AI review text in a consistent markdown template.
        """
        return (
            f"## 🤖 AI Code Review\n\n"
            f"{review_text}\n\n"
            f"---\n"
            f"*Reviewed by [AI PR Reviewer]"
            f"(https://github.com/Deepti63/AI-PR-Reviewer) "
            f"powered by Mistral · Triggered by `@ai-reviewer`*"
        )


# ─────────────────────────────────────────────────────────────
# Quick test — run directly to verify Azure DevOps connection
# python -m azure_devops.client
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from config import load_config, validate_config

    config = load_config()
    validate_config(config)

    client = AzureDevOpsClient(config.azure)

    PR_ID = 1

    pr = client.get_pull_request(PR_ID)

    print("\n" + "=" * 50)
    print(pr.summary)
    print("=" * 50)

    print("\n📁 Files changed:")
    for f in pr.files:
        print(f"   [{f.change_type}] {f.filename}")

    print("\n📝 Full diff preview:")
    preview = pr.full_diff
    print(preview[:500] + "..." if len(preview) > 500 else preview)
