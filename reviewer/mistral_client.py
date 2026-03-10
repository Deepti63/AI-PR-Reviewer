# reviewer/mistral_client.py
# ─────────────────────────────────────────────────────────────
# PURPOSE: Send prompts to Mistral via Ollama and get reviews back.
# Ollama exposes a simple REST API — we just POST to it.
# ─────────────────────────────────────────────────────────────

import requests
from config import MistralConfig
from azure_devops.models import PullRequest
from reviewer.prompt_builder import PromptBuilder


class MistralClient:
    """
    Client for Mistral running locally via Ollama.

    🧠 CONCEPT: Ollama API
    Ollama runs LLMs locally and exposes a REST API.
    Two endpoints we care about:

    POST /api/generate   → single prompt, single response
    POST /api/chat       → multi-turn conversation

    We use /api/generate — simpler, perfect for code review.

    Request shape:
    {
        "model": "mistral",
        "system": "You are a senior engineer...",
        "prompt": "Review this PR...",
        "stream": false      ← wait for full response, not chunks
    }

    Response shape:
    {
        "response": "## AI Code Review\n\n...",
        "done": true,
        "total_duration": 12345678
    }
    """

    def __init__(self, config: MistralConfig):
        self.config = config
        self.prompt_builder = PromptBuilder()

    def review_pull_request(self, pr: PullRequest) -> str:
        """
        Main method — takes a PR, returns a review string.

        🧠 CONCEPT: Single public method
        The caller (main.py) doesn't need to know about
        prompts, Ollama API, or streaming. It just calls:
            review = client.review_pull_request(pr)
        All complexity is hidden inside this class.
        This is called ENCAPSULATION.
        """
        print("🤖 Sending diff to Mistral for review...")

        # Build the prompt from the PR data
        system_prompt = self.prompt_builder.get_system_prompt()
        user_prompt = self.prompt_builder.build_review_prompt(pr)

        # Send to Ollama and get review back
        review = self._call_ollama(system_prompt, user_prompt)

        print("✅ Review received from Mistral")
        return review

    def _call_ollama(self, system_prompt: str, user_prompt: str) -> str:
        """
        Makes the actual HTTP call to Ollama.

        🧠 CONCEPT: stream=False
        Ollama can stream responses token by token (like ChatGPT typing).
        stream=False tells it: wait until done, return everything at once.
        Simpler for our use case — we post the full review at once.

        🧠 CONCEPT: timeout on AI calls
        AI inference takes time — a large diff might take 30-60 seconds.
        We set timeout=120 (2 minutes) to be safe.
        Never use the default (no timeout) — your app would hang forever
        if Ollama crashes or gets stuck.
        """
        payload = {
            "model": self.config.model,
            "system": system_prompt,
            "prompt": user_prompt,
            "stream": False,        # wait for complete response
            "options": {
                "temperature": 0.2, # 🧠 Lower = more focused/deterministic
                                    # Higher = more creative/random
                                    # For code review: low temp = consistent
                "num_predict": 1024 # max tokens in response
            }
        }

        try:
            print(f"   Calling Ollama at {self.config.api_url}...")
            print(f"   Model: {self.config.model}")
            print(f"   This may take 30-60 seconds...")

            response = requests.post(
                self.config.api_url,
                json=payload,
                timeout=120     # AI inference can be slow
            )
            response.raise_for_status()

            data = response.json()

            # 🧠 CONCEPT: Defensive dict access
            # data["response"] crashes if key missing
            # data.get("response", "fallback") returns fallback safely
            review_text = data.get("response", "")

            if not review_text:
                return "❌ Mistral returned an empty response. Try again."

            return review_text.strip()

        except requests.exceptions.ConnectionError:
            raise ConnectionError(
                "❌ Cannot connect to Ollama.\n"
                "   Is Ollama running? Start it with: ollama serve\n"
                "   Then verify Mistral is pulled: ollama pull mistral"
            )

        except requests.exceptions.Timeout:
            raise TimeoutError(
                "❌ Mistral timed out after 120 seconds.\n"
                "   The diff might be too large. Try reducing DIFF_CONTEXT_LINES."
            )

        except requests.exceptions.HTTPError as e:
            raise ValueError(
                f"❌ Ollama API error: {e.response.status_code}\n"
                f"   {e.response.text}"
            ) from e

    def check_ollama_running(self) -> bool:
        """
        Verifies Ollama is up before we try to use it.
        Call this at startup — fail fast with a clear message.

        🧠 CONCEPT: Health check pattern
        Always verify external dependencies at startup.
        Better to crash immediately with a clear message than
        to crash 30 seconds in with a confusing one.
        """
        try:
            # Ollama root endpoint returns basic info if running
            base_url = self.config.api_url.replace("/api/generate", "")
            response = requests.get(base_url, timeout=5)
            return response.status_code == 200
        except Exception:
            return False


# ─────────────────────────────────────────────────────────────
# Quick test — sends a real PR diff to Mistral
# Make sure Ollama is running first: ollama serve
# python -m reviewer.mistral_client
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from config import load_config, validate_config
    from azure_devops.client import AzureDevOpsClient

    config = load_config()
    validate_config(config)

    # Step 1: Check Ollama is running
    mistral = MistralClient(config.mistral)
    if not mistral.check_ollama_running():
        print("❌ Ollama is not running!")
        print("   Start it with: ollama serve")
        exit(1)
    print("✅ Ollama is running")

    # Step 2: Fetch the real PR from Azure DevOps
    azure_client = AzureDevOpsClient(config.azure)
    pr = azure_client.get_pull_request(1)

    print(f"\n📋 Reviewing: {pr.summary}\n")

    # Step 3: Send to Mistral
    review = mistral.review_pull_request(pr)

    # Step 4: Print the review
    print("\n" + "=" * 60)
    print("🤖 AI REVIEW:")
    print("=" * 60)
    print(review)