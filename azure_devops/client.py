# azure_devops/client.py
# ─────────────────────────────────────────────────────────────
# PURPOSE: All communication with Azure DevOps REST API.
# Fetch PR details, diffs, and post review comments.
# ─────────────────────────────────────────────────────────────

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

        🧠 CONCEPT: Single responsibility
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

        🧠 CONCEPT: API versioning
        Azure DevOps requires ?api-version=7.1 on every call.
        Without it, the API returns 400 Bad Request.
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

        🧠 CONCEPT: Azure DevOps diff flow
        Step 1: Get iterations (each push to PR = one iteration)
        Step 2: Get changed files in the latest iteration
        Step 3: For each file, fetch actual content/diff
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

        # Get latest iteration id
        # 🧠 CONCEPT: max() with lambda key
        # lambda x: x["id"] is a tiny anonymous function
        # max() uses it to compare items by their "id" field
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

            # Fetch actual diff for this file
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
        Fetches the actual content/diff for a specific file.

        🧠 CONCEPT: Best-effort fetching
        If this fails for one file, we catch the exception
        and return None — the review continues with other files.
        Never let one file crash the whole review.
        """
        try:
            # Get PR data to find commit IDs
            pr_url = f"{self.git_url}/pullrequests/{pr_id}?api-version=7.1"
            pr_data = self._make_request("GET", pr_url)

            # These are the commit hashes at each end of the PR
            last_merge = pr_data.get("lastMergeSourceCommit", {}).get("commitId")
            first_commit = pr_data.get("lastMergeTargetCommit", {}).get("commitId")

            if not last_merge or not first_commit:
                return f"[Could not retrieve diff for {filename}]"

            # Fetch diff between target and source commits
            diff_url = (
                f"{self.git_url}/diffs/commits"
                f"?api-version=7.1"
                f"&baseVersion={first_commit}"
                f"&baseVersionType=commit"
                f"&targetVersion={last_merge}"
                f"&targetVersionType=commit"
            )
            diff_data = self._make_request("GET", diff_url)

            # Find this specific file in the diff results
            for change in diff_data.get("changes", []):
                item = change.get("item", {})
                if item.get("path") == filename:

                    if change.get("changeType") == "delete":
                        return f"[File deleted: {filename}]"

                    # Fetch file content at the source commit
                    content_url = (
                        f"{self.git_url}/items"
                        f"?path={filename}"
                        f"&version={last_merge}"
                        f"&versionType=commit"
                        f"&api-version=7.1"
                    )
                    # content_response = requests.get(
                    #     content_url,
                    #     headers=self.headers,
                    #     timeout=30
                    # )
                    raw_headers = {**self.headers, "Accept": "text/plain"}
                    content_response = requests.get(
                        content_url,
                        headers=raw_headers,
                        timeout=30
                    )

                    if content_response.status_code == 200:
                        # 🧠 CONCEPT: String slicing
                        # content[:3000] = first 3000 characters
                        # Prevents sending huge files to the AI
                        return content_response.text[:3000]

            return f"[No diff found for {filename}]"

        except Exception as e:
            # Broad except is intentional here — diff is best-effort
            print(f"   ⚠️  Could not fetch diff for {filename}: {e}")
            return None

    def post_pr_comment(
        self,
        pr_id: int,
        review_text: str,
        thread_id: Optional[int] = None
    ) -> bool:
        """
        Posts a review comment to a PR thread.

        🧠 CONCEPT: Two posting modes
        thread_id=None → creates a NEW thread on the PR
        thread_id=123  → replies to an EXISTING thread
                         (used when replying to @ai-reviewer comment)
        """
        formatted = self._format_review(review_text)

        if thread_id:
            # Reply to existing thread
            url = (
                f"{self.git_url}/pullrequests/{pr_id}"
                f"/threads/{thread_id}/comments?api-version=7.1"
            )
            payload = {"content": formatted}
        else:
            # Create a brand new thread
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