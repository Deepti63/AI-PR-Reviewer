# azure_devops.py
import requests
import base64

class AzureDevOpsClient:
    def __init__(self, organization: str, project: str, personal_access_token: str):
        self.organization = organization
        self.project = project
        self.token = personal_access_token
        self.headers = {
            "Authorization": f"Basic {self._encode_pat(self.token)}",
            "Content-Type": "application/json"
        }

    def _encode_pat(self, pat: str) -> str:
        # Azure requires base64 encoding of ":PAT"
        token_bytes = f":{pat}".encode("utf-8")
        return base64.b64encode(token_bytes).decode("utf-8")

    # ----------------------------
    # PR and commit helpers
    # ----------------------------
    def get_pr_commits(self, repo_id: str, pr_id: int):
        """Get source and target commits of a PR"""
        url = f"https://dev.azure.com/{self.organization}/{self.project}/_apis/git/repositories/{repo_id}/pullRequests/{pr_id}?api-version=7.0"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        data = response.json()
        source_commit = data["lastMergeSourceCommit"]["commitId"]
        target_commit = data["lastMergeTargetCommit"]["commitId"]
        return source_commit, target_commit

    def get_latest_iteration_id(self, repo_id: str, pr_id: int):
        """Get the latest iteration of a PR"""
        url = f"https://dev.azure.com/{self.organization}/{self.project}/_apis/git/repositories/{repo_id}/pullRequests/{pr_id}/iterations?api-version=7.0"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        data = response.json()
        return max(iteration["id"] for iteration in data["value"])

    # ----------------------------
    # PR files
    # ----------------------------
    def get_pr_files(self, repo_id: str, pr_id: int):
        """Get all files changed in the PR (latest iteration)"""
        iteration_id = self.get_latest_iteration_id(repo_id, pr_id)
        url = f"https://dev.azure.com/{self.organization}/{self.project}/_apis/git/repositories/{repo_id}/pullRequests/{pr_id}/iterations/{iteration_id}/changes?api-version=7.0"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        data = response.json()
        files = []
        for change in data.get("changes", []):
            path = change["item"]["path"].lstrip("/")
            files.append(path)
        return files

    # ----------------------------
    # File content
    # ----------------------------
    def get_file_content(self, repo_id: str, commit_id: str, file_path: str):
        """Fetch file content at a specific commit"""
        file_path = file_path.lstrip("/")
        url = f"https://dev.azure.com/{self.organization}/{self.project}/_apis/git/repositories/{repo_id}/items"
        params = {
            "scopePath": file_path,
            "versionDescriptor.version": commit_id,
            "includeContent": "true",
            "api-version": "7.0"
        }
        response = requests.get(url, headers=self.headers, params=params)
        if response.status_code == 200:
            return response.json().get("content", "")
        return ""