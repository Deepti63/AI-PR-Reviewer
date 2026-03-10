# main.py
# ─────────────────────────────────────────────────────────────
# PURPOSE: Application entry point.
# Loads config, validates everything, starts the Flask server.
# ─────────────────────────────────────────────────────────────

from config import load_config, validate_config
from app.webhook_server import create_app
from reviewer.mistral_client import MistralClient


def main():
    """
    Starts the AI PR Reviewer webhook server.

    🧠 CONCEPT: Startup sequence
    Good apps follow this pattern at startup:
    1. Load config
    2. Validate config (fail fast if missing)
    3. Check external dependencies (Ollama running?)
    4. Start the server

    If any step fails, crash immediately with a clear message.
    Never start in a broken state.
    """
    print("🚀 Starting AI PR Reviewer...")
    print("=" * 50)

    # Step 1 + 2: Load and validate config
    config = load_config()
    validate_config(config)

    # Step 3: Check Ollama is running
    mistral = MistralClient(config.mistral)
    if not mistral.check_ollama_running():
        print("❌ Ollama is not running!")
        print("   Start it with: ollama serve")
        print("   Then pull Mistral: ollama pull mistral")
        exit(1)
    print("✅ Ollama is running")

    # Step 4: Create and start Flask server
    app = create_app(config)

    print("\n📡 Server starting...")
    print(f"   Webhook URL : http://localhost:5000/webhook")
    print(f"   Health check: http://localhost:5000/health")
    print(f"\n   Configure Azure DevOps to POST to:")
    print(f"   http://YOUR_SERVER_IP:5000/webhook")
    print("=" * 50)

    # debug=False for production
    # host="0.0.0.0" makes it accessible from outside localhost
    # (needed when Azure DevOps calls your VM)
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )


if __name__ == "__main__":
    main()