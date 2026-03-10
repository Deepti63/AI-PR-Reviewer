# config.py
# ─────────────────────────────────────────────────────────────
# PURPOSE: Single source of truth for all app configuration.
# Loads from .env file and validates everything is present
# before the app does any real work.
# ─────────────────────────────────────────────────────────────

import os
from dotenv import load_dotenv
from dataclasses import dataclass

# Load .env file into environment variables
# Must happen before any os.environ.get() calls
load_dotenv()


@dataclass
class GitHubConfig:
    """
    Holds GitHub connection settings.

    🧠 CONCEPT: @dataclass
    Instead of writing a full class with __init__, dataclass
    auto-generates it. These two are identical:

    # Without dataclass:             # With dataclass:
    class GitHubConfig:              @dataclass
        def __init__(self,           class GitHubConfig:
            token, owner, repo):         token: str
            self.token = token           owner: str
            self.owner = owner           repo: str
            self.repo = repo
    """
    token: str
    owner: str
    repo: str


@dataclass
class MistralConfig:
    """Holds Mistral/Ollama connection settings."""
    api_url: str
    model: str


@dataclass
class AppConfig:
    """
    Master config object — passed around the whole app.

    🧠 CONCEPT: Composition
    Instead of one giant config object, we nest smaller
    focused configs inside. Clean and organized.
    Usage: config.github.token, config.mistral.model
    """
    github: GitHubConfig
    mistral: MistralConfig


def load_config() -> AppConfig:
    """
    Reads environment variables and builds the AppConfig.

    🧠 CONCEPT: -> AppConfig (return type hint)
    This is documentation built into the code. Your IDE
    will autocomplete config.github.token because it KNOWS
    what type this function returns. No guessing.
    """
    github_config = GitHubConfig(
        token=os.environ.get("GITHUB_TOKEN", ""),
        owner=os.environ.get("GITHUB_REPO_OWNER", ""),
        repo=os.environ.get("GITHUB_REPO_NAME", ""),
    )

    mistral_config = MistralConfig(
        api_url=os.environ.get("MISTRAL_API_URL", "http://localhost:11434/api/generate"),
        model=os.environ.get("MISTRAL_MODEL", "mistral"),
    )

    return AppConfig(github=github_config, mistral=mistral_config)


def validate_config(config: AppConfig) -> None:
    """
    Validates all required fields are present.
    Fails LOUDLY and EARLY if anything is missing.

    🧠 CONCEPT: Fail Fast
    It's better to crash immediately with a clear message
    than to crash later with a confusing one. Always
    validate at the boundaries of your system.

    🧠 CONCEPT: List comprehension
    missing = [name for name, value in items if not value]
    
    This is shorthand for:
    missing = []
    for name, value in items:
        if not value:
            missing.append(name)
    """
    required = {
        "GITHUB_TOKEN": config.github.token,
        "GITHUB_REPO_OWNER": config.github.owner,
        "GITHUB_REPO_NAME": config.github.repo,
    }

    # List comprehension — collects names of empty fields
    missing = [name for name, value in required.items() if not value]

    if missing:
        raise ValueError(
            f"❌ Missing required environment variables:\n"
            f"   {', '.join(missing)}\n"
            f"   → Copy .env.example to .env and fill in your values."
        )

    print("✅ Config loaded and validated successfully!")


# ─────────────────────────────────────────────────────────────
# 🧠 CONCEPT: if __name__ == "__main__"
#
# Python sets __name__ = "__main__" when a file is run directly
# Python sets __name__ = "config"   when a file is imported
#
# This block ONLY runs on direct execution: python config.py
# It is SKIPPED when main.py does: from config import load_config
#
# Use it to test individual modules without running the whole app.
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    config = load_config()
    validate_config(config)

    print(f"\n📋 Configuration Summary:")
    print(f"   GitHub Owner : {config.github.owner}")
    print(f"   GitHub Repo  : {config.github.repo}")
    print(f"   GitHub Token : {'*' * len(config.github.token)}")
    print(f"   Mistral URL  : {config.mistral.api_url}")
    print(f"   Mistral Model: {config.mistral.model}")