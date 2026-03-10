# app/event_handler.py
# ─────────────────────────────────────────────────────────────
# PURPOSE: Parse incoming webhook events and decide
# whether to trigger a review or ignore the event.
# ─────────────────────────────────────────────────────────────

import json
from azure_devops.models import WebhookComment


class EventHandler:
    """
    Handles incoming Azure DevOps webhook events.

    Parses the webhook payload and decides if we should
    trigger a review. Single responsibility — no API calls here.
    """

    TRIGGER_PHRASE = "@ai-reviewer"

    # All known Azure DevOps PR comment event types
    SUPPORTED_EVENTS = [
        "ms.vss-code.pull-request-comment-event",
        "ms.vss-code.git-pullrequest-comment-event",
    ]

    def parse_comment_event(self, payload: dict) -> WebhookComment | None:
        """
        Parses a webhook payload.
        Returns WebhookComment if it should trigger a review.
        Returns None if it should be ignored.
        """
        try:
            # Step 1: Check event type
            event_type = payload.get("eventType", "")
            if event_type not in self.SUPPORTED_EVENTS:
                print(f"⏭️  Ignoring event type: {event_type}")
                return None

            resource = payload.get("resource", {})

            # Step 2: Extract comment content
            # Azure DevOps sends resource AS the comment for
            # git-pullrequest-comment-event — content is at top level
            content = self._extract_comment_content(resource)
            print(f"📝 Extracted comment: '{content}'")

            if not content:
                print("⚠️  Empty comment content — ignoring")
                return None

            # Step 3: Check trigger phrase
            # Handles "@ai-reviewer" and "@ai-reviewer 10"
            if not content.lower().startswith(self.TRIGGER_PHRASE.lower()):
                print(f"⏭️  Ignoring comment: '{content[:50]}'")
                return None

            # Step 4: Parse optional context lines
            # "@ai-reviewer"    → None (use config default)
            # "@ai-reviewer 10" → 10
            context_lines = self._parse_context_lines(content)

            # Step 5: Extract PR id
            pr = resource.get("pullRequest", {})
            pr_id = pr.get("pullRequestId")
            print(f"   PR object found: {pr}")
            print(f"   Full resource keys: {list(resource.keys())}")

            # Fallback: extract from _links URL
            # URL: https://.../pullRequests/1/threads/16/comments/1
            if not pr_id:
                try:
                    self_url = (
                        resource
                        .get("_links", {})
                        .get("pullRequests", {})
                        .get("href", "")
                    )
                    if "/pullRequests/" in self_url:
                        pr_id = int(self_url.split("/pullRequests/")[1].split("/")[0])
                        print(f"   Extracted PR id from URL: {pr_id}")
                except Exception:
                    pass
            if not pr_id:
                print("⚠️  Could not extract PR id from payload")
                return None

            # Step 6: Extract thread id so we reply in the same thread
            thread_id = self._extract_thread_id(resource)

            repo = pr.get("repository", {})
            project = repo.get("project", {}).get("name", "")
            repo_id = repo.get("id", "")

            print(f"✅ Trigger detected: '{content}' on PR #{pr_id}")
            print(f"   Thread id: {thread_id}")
            if context_lines is not None:
                print(f"   Context lines override: {context_lines}")

            return WebhookComment(
                pr_id=pr_id,
                comment_content=content,
                comment_id=resource.get("id", 0),
                thread_id=thread_id or 0,
                project=project,
                repo_id=repo_id,
                context_lines=context_lines
            )

        except Exception as e:
            print(f"❌ Error parsing webhook payload: {e}")
            return None

    def _extract_comment_content(self, resource: dict) -> str:
        """
        Tries multiple locations to find the comment text.

        🧠 CONCEPT: Defensive extraction
        Azure DevOps has changed payload structure across versions.
        We try multiple known locations and return the first
        non-empty one. Resilient to API changes.

        Known structures:
        1. resource.content              ← git-pullrequest-comment-event
                                           resource IS the comment
        2. resource.comment.content      ← older event format
        3. resource.comment.text         ← even older format
        4. resource.thread.comments[0]   ← thread-level events
        """
        # Location 1: resource IS the comment (most recent Azure DevOps)
        # This is what git-pullrequest-comment-event sends
        content = resource.get("content", "").strip()
        if content:
            return content

        # Location 2: resource → comment → content
        comment = resource.get("comment", {})
        content = comment.get("content", "").strip()
        if content:
            return content

        # Location 3: resource → comment → text
        content = comment.get("text", "").strip()
        if content:
            return content

        # Location 4: resource → thread → comments → first item
        thread = resource.get("thread", {})
        comments = thread.get("comments", [])
        if comments:
            content = comments[0].get("content", "").strip()
            if content:
                return content

        return ""

    def _extract_thread_id(self, resource: dict) -> int | None:
        """
        Extracts the thread id so we can reply in the same thread.

        🧠 CONCEPT: Fallback chain
        We try the structured field first (clean).
        If not found, we parse it from the URL (hacky but reliable).

        URL format:
        https://.../pullRequests/1/threads/16/comments/1
                                          ^^
                                     thread id = 16
        """
        # Try structured field first
        thread_context = resource.get("pullRequestThreadContext", {})
        thread_id = thread_context.get("threadId", None)
        if thread_id:
            return thread_id

        # Fallback: parse from _links.threads.href URL
        try:
            threads_url = (
                resource
                .get("_links", {})
                .get("threads", {})
                .get("href", "")
            )
            if "/threads/" in threads_url:
                # Split on /threads/ and take the number after it
                # "https://.../threads/16/comments/1" → "16"
                thread_id = int(
                    threads_url.split("/threads/")[1].split("/")[0]
                )
                print(f"   Extracted thread id from URL: {thread_id}")
                return thread_id
        except Exception:
            pass

        return None

    def _parse_context_lines(self, content: str) -> int | None:
        """
        Parses optional context line count from comment.

        "@ai-reviewer"    → None (use config default)
        "@ai-reviewer 10" → 10
        "@ai-reviewer 0"  → 0 (diff only, no context)

        🧠 CONCEPT: int() conversion with try/except
        int("10") = 10   ← works
        int("abc") = ValueError  ← we catch this and return None
        """
        parts = content.strip().split()

        # Just "@ai-reviewer" — no number
        if len(parts) == 1:
            return None

        # "@ai-reviewer 10" — try to parse the number
        if len(parts) == 2:
            try:
                lines = int(parts[1])
                if 0 <= lines <= 50:
                    return lines
                else:
                    print(f"⚠️  Context lines {lines} out of range (0-50)")
                    return None
            except ValueError:
                return None

        return None
