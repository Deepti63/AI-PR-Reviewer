# azure_devops/models.py
# ─────────────────────────────────────────────────────────────
# PURPOSE: Data shapes for Azure DevOps API objects.
# We model exactly what we need — nothing more.
# ─────────────────────────────────────────────────────────────

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class PRFile:
    """
    Represents a single file changed in a PR.

    🧠 CONCEPT: Why model the data?
    The Azure DevOps API returns huge JSON blobs with 50+ fields.
    We only need 4-5 of them. By mapping to our own model:
    1. The rest of our code is clean — pr_file.filename not pr_file["item"]["path"]
    2. If the API changes, we fix it in ONE place (the client)
    3. Our models are self-documenting
    """
    filename: str           # e.g. "src/utils/helper.py"
    change_type: str        # "add", "edit", "delete"
    diff: Optional[str] = None  # the actual code diff — we fetch this separately


@dataclass
class PullRequest:
    """Represents an Azure DevOps Pull Request."""
    id: int
    title: str
    description: str
    author: str
    source_branch: str      # the feature branch
    target_branch: str      # usually main/master
    files: List[PRFile] = field(default_factory=list)

    @property
    def summary(self) -> str:
        """
        Human readable summary of this PR.
        🧠 CONCEPT: @property — computed attribute, not stored data.
        """
        return (
            f"PR #{self.id}: {self.title}\n"
            f"Author  : {self.author}\n"
            f"Branch  : {self.source_branch} → {self.target_branch}\n"
            f"Files   : {len(self.files)} changed"
        )

    @property
    def full_diff(self) -> str:
        """
        Concatenates all file diffs into one string for the AI.
        🧠 CONCEPT: Generator expression inside join()
        Instead of building a list then joining, we generate
        each chunk on the fly — more memory efficient.
        """
        chunks = []
        for f in self.files:
            if f.diff:
                chunks.append(
                    f"### File: {f.filename} ({f.change_type})\n"
                    f"```\n{f.diff}\n```"
                )
        return "\n\n".join(chunks)


@dataclass
class WebhookComment:
    """
    Represents the parsed data from an Azure DevOps webhook event.
    This is what arrives when someone comments on a PR.

    🧠 CONCEPT: Modelling incoming data
    Webhooks send raw JSON. We parse it ONCE at the boundary
    and work with clean objects everywhere else.
    """
    pr_id: int
    comment_content: str    # the actual comment text e.g. "@ai-reviewer"
    comment_id: int         # needed to reply in the same thread
    thread_id: int          # the thread this comment belongs to
    project: str
    repo_id: str
    context_lines: int | None = None