# # main.py
# from fastapi import FastAPI
# from app.azure_devops import AzureDevOpsClient
# from utils.diff_utils import compute_diff_with_context

# # FastAPI app
# app = FastAPI()

# # Configure Azure DevOps client
# client = AzureDevOpsClient(
#     organization="deeptisimba",        # replace with your org
#     project="devops",                  # replace with your project
#     personal_access_token=""   # replace with your Azure DevOps PAT
# )# main.py
# main.py
from fastapi import FastAPI
from app.azure_devops import AzureDevOpsClient
from utils.diff_utils import compute_diff_with_context
from app.mistral import generate_pr_review

app = FastAPI()

# ----------------------------
# Configure Azure DevOps client
# ----------------------------
client = AzureDevOpsClient(
    organization="deeptisimba",        # your org
    project="devops",                  # your project
    personal_access_token=""
    personal_access_token=""

)

# Simulated PR files (replace with real Azure DevOps files later)
SAMPLE_PR_FILES = {
    "image/Dockerfile": "# syntax=docker/dockerfile:1.4\n#test\nARG ARCH\nARG NAME\nFROM $NAME-base:latest-$ARCH",
    "Gemfile": "source 'https://rubygems.org'\ngem 'rails', '~>6.1'\ngem 'puma', '~>5.0'"
}

@app.get("/pr-review-ai")
def pr_review_ai():
    """
    Generate AI review comments for PR files.
    """
    pr_files = SAMPLE_PR_FILES  # temporary: simulated files
    reviews = generate_pr_review(pr_files)
    return reviews
# ----------------------------
# PR review endpoint
# ----------------------------
@app.get("/pr-review")
def pr_review(repo_id: str, pr_id: int, context_lines: int = 0):
    """
    Return full file contents for all changed files in a PR.
    context_lines is ignored for now, we send the whole file.
    """
    source_commit, target_commit = client.get_pr_commits(repo_id, pr_id)
    files = client.get_pr_files(repo_id, pr_id)

    pr_contents = {}
    for file in files:
        content = client.get_file_content(repo_id, source_commit, file) or ""
        pr_contents[file] = content

    # Here is where you would send `pr_contents` to Mistral AI for review
    return pr_contents