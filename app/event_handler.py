# app/event_handler.py
# ─────────────────────────────────────────────────────────────
# PURPOSE: Parse incoming webhook events and decide
# whether to trigger a review or ignore the event.
# ─────────────────────────────────────────────────────────────

from azure_devops.models import WebhookComment


class EventHandler:
    """
    Handles incoming Azure DevOps webhook events.

    🧠 CONCEPT: Single Responsibility
    This class has ONE job — parse the webhook payload
    and decide if we should trigger a review.
    It knows nothing about Mistral or Azure DevOps API calls.
    That logic lives in main.py (the orchestrator).

    🧠 CONCEPT: Azure DevOps Webhook Payload
    When someone comments on a PR, Azure DevOps sends:
    {
        "eventType": "ms.vss-code.pull-request-comment-event",
        "resource": {
            "comment": {
                "id": 1,
                "content": "@ai-reviewer",    ← what we check
                "commentType": 1
            },
            "pullRequest": {
                "pullRequestId": 42,
                "repository": {
                    "id": "repo-uuid",
                    "project": { "name": "devops" }
                }
            }
        }
    }
    """

    # The trigger phrase — only this exact comment starts a review
    # 🧠 CONCEPT: Class constant
    # Defined here so changing the trigger means changing ONE line
    TRIGGER_PHRASE = "@ai-reviewer"

    def parse_comment_event(self, payload: dict) -> WebhookComment | None:
        """
        Parses a webhook payload and returns a WebhookComment
        if it should trigger a review, or None if it should be ignored.

        🧠 CONCEPT: Return None as a signal
        Returning None means "nothing to do here".
        The caller checks: if result is None → skip
        This is cleaner than raising exceptions for normal flow.

        🧠 CONCEPT: .strip().lower()
        Strip removes leading/trailing whitespace
        Lower converts to lowercase
        Together they handle: "@AI-Reviewer ", "@ai-reviewer", "@AI-REVIEWER"
        All treated the same — case insensitive matching.
        """
        try:
            # Check event type — we only handle PR comment events
            event_type = payload.get("eventType", "")
            if event_type != "ms.vss-code.pull-request-comment-event":
                print(f"⏭️  Ignoring event type: {event_type}")
                return None

            resource = payload.get("resource", {})

            # Extract the comment content
            comment = resource.get("comment", {})
            content = comment.get("content", "").strip()

            # Parse context lines if user provided them
            # Handles: "@ai-reviewer" and "@ai-reviewer 10"
            context_lines = self._parse_context_lines(content)

            # Check if this comment is our trigger phrase
            # 🧠 CONCEPT: .lower().startswith()
            # startswith checks if string begins with a prefix
            # We use it so "@ai-reviewer 10" also triggers a review
            if not content.lower().startswith(self.TRIGGER_PHRASE.lower()):
                print(f"⏭️  Ignoring comment: '{content[:50]}'")
                return None

            # Extract PR details
            pr = resource.get("pullRequest", {})
            pr_id = pr.get("pullRequestId")

            if not pr_id:
                print("⚠️  Could not extract PR id from webhook payload")
                return None

            # Azure DevOps sends thread context here
            thread_context = resource.get("pullRequestThreadContext", {})
            thread_id = thread_context.get("threadId", None)

            # If no thread id found, post as new thread (None = new thread)
            if not thread_id:
                print("   No thread id found — will create new thread")
                thread_id = None

            repo = pr.get("repository", {})
            project = repo.get("project", {}).get("name", "")
            repo_id = repo.get("id", "")

            print(f"✅ Trigger detected: '{content}' on PR #{pr_id}")
            if context_lines is not None:
                print(f"   Context lines override: {context_lines}")

            return WebhookComment(
                pr_id=pr_id,
                comment_content=content,
                comment_id=comment.get("id", 0),
                thread_id=thread_id or 0,
                project=project,
                repo_id=repo_id,
                context_lines=context_lines   # None = use default from config
            )

        except Exception as e:
            print(f"❌ Error parsing webhook payload: {e}")
            return None

    def _parse_context_lines(self, content: str) -> int | None:
        """
        Parses optional context line count from comment.

        🧠 CONCEPT: String splitting
        "@ai-reviewer 10".split() → ["@ai-reviewer", "10"]
        parts[1] = "10" → int("10") = 10

        Returns None if no number provided (use config default).
        Returns the int if a valid number was found.

        This is the Phase 6 feature we planned in the backlog!
        """
        parts = content.strip().split()

        # Just "@ai-reviewer" with no number
        if len(parts) == 1:
            return None

        # "@ai-reviewer 10" — try to parse the number
        if len(parts) == 2:
            try:
                lines = int(parts[1])
                # Sanity check — reasonable range only
                if 0 <= lines <= 50:
                    return lines
                else:
                    print(f"⚠️  Context lines {lines} out of range (0-50), using default")
                    return None
            except ValueError:
                # Not a number — ignore
                return None

        return None