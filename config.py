# config.py
import os
from dotenv import load_dotenv
from dataclasses import dataclass

load_dotenv()


@dataclass
class AzureDevOpsConfig:
    """
    Holds Azure DevOps connection settings.

    🧠 CONCEPT: How Azure DevOps API auth works
    Azure DevOps uses Basic Auth with a PAT token.
    The token is base64 encoded as ":PAT" (note the colon prefix).
    We'll handle that encoding in the client, not here.
    """
    org_url: str        # https://dev.azure.com/deeptisimba
    project: str        # your project name
    repo: str           # your repo name
    pat: str            # Personal Access Token


@dataclass
class MistralConfig:
    """Holds Mistral/Ollama connection settings."""
    api_url: str
    model: str


@dataclass
class AppConfig:
    """Master config — bundles everything together."""
    azure: AzureDevOpsConfig
    mistral: MistralConfig
    webhook_secret: str     # for verifying Azure DevOps webhook requests


def load_config() -> AppConfig:
    """Reads environment variables and returns a fully built AppConfig."""
    azure_config = AzureDevOpsConfig(
        org_url=os.environ.get("AZURE_DEVOPS_ORG_URL", ""),
        project=os.environ.get("AZURE_DEVOPS_PROJECT", ""),
        repo=os.environ.get("AZURE_DEVOPS_REPO", ""),
        pat=os.environ.get("AZURE_DEVOPS_PAT", ""),
    )

    mistral_config = MistralConfig(
        api_url=os.environ.get("MISTRAL_API_URL", "http://localhost:11434/api/generate"),
        model=os.environ.get("MISTRAL_MODEL", "mistral"),
    )

    return AppConfig(
        azure=azure_config,
        mistral=mistral_config,
        webhook_secret=os.environ.get("WEBHOOK_SECRET", ""),
    )


def validate_config(config: AppConfig) -> None:
    """Validates all required fields are present. Fails fast if missing."""
    required = {
        "AZURE_DEVOPS_ORG_URL": config.azure.org_url,
        "AZURE_DEVOPS_PROJECT": config.azure.project,
        "AZURE_DEVOPS_REPO": config.azure.repo,
        "AZURE_DEVOPS_PAT": config.azure.pat,
        "WEBHOOK_SECRET": config.webhook_secret,
    }

    missing = [name for name, value in required.items() if not value]

    if missing:
        raise ValueError(
            f"❌ Missing required environment variables:\n"
            f"   {', '.join(missing)}\n"
            f"   → Copy .env.example to .env and fill in your values."
        )

    print("✅ Config loaded and validated successfully!")


if __name__ == "__main__":
    config = load_config()
    validate_config(config)

    print(f"\n📋 Configuration Summary:")
    print(f"   Azure Org     : {config.azure.org_url}")
    print(f"   Azure Project : {config.azure.project}")
    print(f"   Azure Repo    : {config.azure.repo}")
    print(f"   PAT Token     : {'*' * len(config.azure.pat)}")
    print(f"   Mistral URL   : {config.mistral.api_url}")
    print(f"   Mistral Model : {config.mistral.model}")
    print(f"   Webhook Secret: {'*' * len(config.webhook_secret)}")