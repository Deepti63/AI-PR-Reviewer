# app/webhook_server.py
# ─────────────────────────────────────────────────────────────
# PURPOSE: Flask HTTP server that receives Azure DevOps webhooks.
# Validates the request, parses it, triggers the review.
# ─────────────────────────────────────────────────────────────

import hmac
import hashlib
import json
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

    This is the standard Flask pattern for production apps.
    """
    app = Flask(__name__)

    # Create our service clients once — reuse across requests
    event_handler = EventHandler()
    azure_client = AzureDevOpsClient(config.azure)
    mistral_client = MistralClient(config.mistral)

    @app.route("/health", methods=["GET"])
    def health_check():
        """
        Health check endpoint.
        Azure DevOps and monitoring tools call this to verify
        the server is up before sending real webhooks.

        🧠 CONCEPT: Route decorator
        @app.route("/health") tells Flask:
        "When a GET request hits /health, run this function"
        """
        return jsonify({
            "status": "healthy",
            "service": "ai-pr-reviewer",
            "ollama": mistral_client.check_ollama_running()
        }), 200

    @app.route("/webhook", methods=["POST"])
    def webhook():
        """
        Main webhook endpoint — Azure DevOps posts here.

        Flow:
        1. Validate the webhook secret (security)
        2. Parse the JSON payload
        3. Check if it's an @ai-reviewer comment
        4. Fetch PR diff from Azure DevOps
        5. Send to Mistral for review
        6. Post review back to PR
        7. Return 200 OK to Azure DevOps

        🧠 CONCEPT: Always return 200 to webhooks
        Azure DevOps expects a 200 response quickly.
        If it times out waiting, it will retry — causing
        duplicate reviews. So we acknowledge first,
        then do the work. (We'll improve this in Phase 5
        with async processing.)
        """
        # Step 1: Validate webhook secret
        if not _validate_webhook_secret(request, config.webhook_secret):
            print("❌ Invalid webhook secret — request rejected")
            return jsonify({"error": "Unauthorized"}), 401

        # Step 2: Parse the JSON payload
        try:
            payload = request.get_json(force=True)
            if not payload:
                return jsonify({"error": "Empty payload"}), 400
        except Exception:
            return jsonify({"error": "Invalid JSON"}), 400

        print(f"\n{'='*50}")
        print(f"📨 Webhook received: {payload.get('eventType', 'unknown')}")

        # Step 3: Parse the event — is it an @ai-reviewer comment?
        webhook_comment = event_handler.parse_comment_event(payload)

        if webhook_comment is None:
            # Not our trigger — ignore silently
            return jsonify({"status": "ignored"}), 200

        # Step 4 + 5 + 6: Fetch PR, review, post comment
        try:
            # Override context lines if user specified in comment
            # e.g. "@ai-reviewer 10" → use 10 lines of context
            if webhook_comment.context_lines is not None:
                config.azure.diff_context_lines = webhook_comment.context_lines
                print(f"   Using {webhook_comment.context_lines} context lines")

            # Fetch the PR and its diff
            pr = azure_client.get_pull_request(webhook_comment.pr_id)

            # Send to Mistral
            review = mistral_client.review_pull_request(pr)

            # Post back to PR — reply in the same thread
            azure_client.post_pr_comment(
                pr_id=webhook_comment.pr_id,
                review_text=review,
                thread_id=webhook_comment.thread_id
            )

            return jsonify({
                "status": "review_posted",
                "pr_id": webhook_comment.pr_id
            }), 200

        except ConnectionError as e:
            # Ollama not running
            print(f"❌ Connection error: {e}")
            return jsonify({"error": str(e)}), 503

        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            return jsonify({"error": "Internal server error"}), 500

    def _validate_webhook_secret(req, secret: str) -> bool:
        """
        Validates the webhook came from Azure DevOps.

        🧠 CONCEPT: Webhook security
        Anyone could POST to your /webhook endpoint.
        Azure DevOps signs each request with a shared secret
        using HMAC-SHA1. We verify the signature matches.

        Without this check, anyone could trigger fake reviews
        or spam your server.

        🧠 CONCEPT: hmac.compare_digest()
        Never use == to compare secrets.
        == is vulnerable to timing attacks — an attacker can
        measure response time to guess the secret byte by byte.
        compare_digest takes constant time regardless of match.
        """
        if not secret:
            # No secret configured — skip validation in dev
            print("⚠️  No webhook secret configured — skipping validation")
            return True

        # Azure DevOps sends signature in this header
        signature = req.headers.get("X-Hub-Signature", "")

        if not signature:
            return False

        # Compute expected signature
        mac = hmac.new(
            secret.encode("utf-8"),
            msg=req.data,
            digestmod=hashlib.sha1
        )
        expected = f"sha1={mac.hexdigest()}"

        # 🧠 Constant-time comparison — security best practice
        return hmac.compare_digest(expected, signature)

    return app