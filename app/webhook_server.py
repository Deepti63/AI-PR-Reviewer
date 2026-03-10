# app/webhook_server.py
# ─────────────────────────────────────────────────────────────
# PURPOSE: Flask HTTP server that receives Azure DevOps webhooks.
# Validates the request, parses it, triggers the review.
# ─────────────────────────────────────────────────────────────

import hmac
import hashlib
import threading
from flask import Flask, request, jsonify
from config import AppConfig
from app.event_handler import EventHandler
from azure_devops.client import AzureDevOpsClient
from reviewer.mistral_client import MistralClient


def create_app(config: AppConfig) -> Flask:
    """
    Creates and configures the Flask application.

    🧠 CONCEPT: App Factory Pattern
    Instead of creating Flask app at module level,
    we create it inside a function. This means:
    1. Config is injected — no global state
    2. Easy to test — create app with test config
    3. Multiple instances possible if needed
    """
    app = Flask(__name__)

    # Create service clients once — reuse across all requests
    event_handler = EventHandler()
    azure_client = AzureDevOpsClient(config.azure)
    mistral_client = MistralClient(config.mistral)

    # ─────────────────────────────────────────────────────────
    # 🧠 CONCEPT: Deduplication set
    # Azure DevOps retries the webhook if it doesn't get a
    # fast response. Mistral takes 30-60s → Azure retries →
    # multiple reviews posted.
    #
    # Fix: track which PRs are currently being reviewed.
    # If a review is already in progress for PR #X, ignore
    # any new webhooks for PR #X until it finishes.
    # ─────────────────────────────────────────────────────────
    reviews_in_progress = set()

    @app.route("/health", methods=["GET"])
    def health_check():
        """
        Health check endpoint.
        Azure DevOps and monitoring tools call this to verify
        the server is up before sending real webhooks.
        """
        return jsonify({
            "status": "healthy",
            "service": "ai-pr-reviewer",
            "ollama": mistral_client.check_ollama_running(),
            "reviews_in_progress": list(reviews_in_progress)
        }), 200

    @app.route("/webhook", methods=["POST"])
    def webhook():
        """
        Main webhook endpoint — Azure DevOps posts here.

        🧠 CONCEPT: Acknowledge first, work later
        Azure DevOps expects a 200 response quickly (within 5s).
        If it times out waiting, it retries → duplicate reviews.

        Solution:
        1. Parse and validate the request (fast)
        2. Return 200 immediately
        3. Do the actual review work in a background thread

        This way Azure DevOps never times out and never retries.
        """
        # Step 1: Validate webhook secret
        if not _validate_webhook_secret(request, config.webhook_secret):
            print("❌ Invalid webhook secret — request rejected")
            return jsonify({"error": "Unauthorized"}), 401

        # Step 2: Parse JSON payload
        try:
            payload = request.get_json(force=True)
            if not payload:
                return jsonify({"error": "Empty payload"}), 400
        except Exception:
            return jsonify({"error": "Invalid JSON"}), 400

        print(f"\n{'='*50}")
        print(f"📨 Webhook received: {payload.get('eventType', 'unknown')}")

        # Step 3: Parse the event
        webhook_comment = event_handler.parse_comment_event(payload)

        if webhook_comment is None:
            # Not our trigger — ignore silently
            return jsonify({"status": "ignored"}), 200

        pr_id = webhook_comment.pr_id

        # Step 4: Deduplication check
        # 🧠 CONCEPT: set membership check — O(1) lookup
        # 'in' on a set is instant regardless of set size
        if pr_id in reviews_in_progress:
            print(f"⏭️  Review already in progress for PR #{pr_id} — ignoring duplicate")
            return jsonify({
                "status": "duplicate_ignored",
                "pr_id": pr_id
            }), 200

        # Mark this PR as being reviewed
        reviews_in_progress.add(pr_id)

        # Step 5: Start background thread for the actual review
        # 🧠 CONCEPT: threading.Thread
        # Creates a new thread that runs _process_review() independently.
        # Our webhook() function returns 200 immediately while the
        # review happens in the background.
        #
        # daemon=True means the thread won't block app shutdown —
        # when main thread exits, background threads exit too.
        thread = threading.Thread(
            target=_process_review,
            args=(webhook_comment, azure_client, mistral_client, config, reviews_in_progress),
            daemon=True
        )
        thread.start()

        # Return 200 immediately — before Mistral even starts
        return jsonify({
            "status": "review_started",
            "pr_id": pr_id
        }), 200

    def _validate_webhook_secret(req, secret: str) -> bool:
        """
        Validates the webhook came from Azure DevOps.

        🧠 CONCEPT: HMAC signature verification
        Azure DevOps signs each request with a shared secret.
        We verify the signature matches before processing.

        🧠 CONCEPT: hmac.compare_digest()
        Never use == to compare secrets — vulnerable to timing attacks.
        compare_digest() takes constant time regardless of match.
        """
        if not secret:
            print("⚠️  No webhook secret configured — skipping validation")
            return True

        signature = req.headers.get("X-Hub-Signature", "")
        if not signature:
            return False

        mac = hmac.new(
            secret.encode("utf-8"),
            msg=req.data,
            digestmod=hashlib.sha1
        )
        expected = f"sha1={mac.hexdigest()}"
        return hmac.compare_digest(expected, signature)

    return app


def _process_review(webhook_comment, azure_client, mistral_client, config, reviews_in_progress):
    """
    Runs in a background thread.
    Fetches PR diff, gets AI review, posts comment back to PR.

    🧠 CONCEPT: Why this is outside create_app()
    Threading works better with module-level functions.
    We pass everything it needs as arguments — no hidden state.

    🧠 CONCEPT: try/finally
    finally block ALWAYS runs — even if an exception occurs.
    We use it to remove the PR from reviews_in_progress so
    future @ai-reviewer comments on the same PR will work.

    try:
        do the work
    except:
        handle errors
    finally:
        always clean up ← runs no matter what
    """
    pr_id = webhook_comment.pr_id

    try:
        print(f"🔄 Background review started for PR #{pr_id}")

        # Override context lines if user specified
        # e.g. "@ai-reviewer 10" → use 10 lines of context
        if webhook_comment.context_lines is not None:
            config.azure.diff_context_lines = webhook_comment.context_lines
            print(f"   Using {webhook_comment.context_lines} context lines")

        # Fetch PR and diff from Azure DevOps
        pr = azure_client.get_pull_request(pr_id)

        # Send to Mistral for review
        review = mistral_client.review_pull_request(pr)

        # Post review back to PR thread
        azure_client.post_pr_comment(
            pr_id=pr_id,
            review_text=review,
            thread_id=webhook_comment.thread_id
        )

        print(f"✅ Review complete for PR #{pr_id}")

    except ConnectionError as e:
        print(f"❌ Ollama not running: {e}")

    except Exception as e:
        print(f"❌ Review failed for PR #{pr_id}: {e}")

    finally:
        # Always remove from in-progress set when done
        # This allows future reviews on the same PR
        reviews_in_progress.discard(pr_id)
        print(f"🔓 PR #{pr_id} unlocked for future reviews")