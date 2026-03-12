# AI-PR-Reviewer

Automated code review powered by Mistral AI — triggered by commenting `@ai-reviewer` on any Pull Request.

Basic function of this code is if you commment @ai-reviewer in youe pull request it submits PR for reviews from Azure DevOps to your AI in our case its open source ollama (Mistral). Backend uses Python script that leverages Open source AI to automatically review pr changes by sending git diff to AI. It pushes pr through our prompt to review change and provide structured feedback as a comment on your PR . A screenshot is added at the end of this to show the expected output.

![Python](https://img.shields.io/badge/Python-3.11+-blue?style=flat-square&logo=python)
![Flask](https://img.shields.io/badge/Flask-3.0-green?style=flat-square&logo=flask)
![Mistral](https://img.shields.io/badge/Mistral-AI-orange?style=flat-square)
![Azure DevOps](https://img.shields.io/badge/Azure_DevOps-webhook-blue?style=flat-square&logo=azure-devops)
![License](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        TRIGGER                                  │
│           Developer comments "@ai-reviewer" on PR              │
└─────────────────────────┬───────────────────────────────────────┘
                          │ Azure DevOps Webhook
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FLASK WEBHOOK SERVER                         │
│                                                                 │
│  1. Validate request                                            │
│  2. Parse comment event                                         │
│  3. Return 200 immediately (prevent retries)                    │
│  4. Spawn background thread                                     │
└─────────────────────────┬───────────────────────────────────────┘
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
┌─────────────────────┐   ┌─────────────────────┐
│  Azure DevOps API   │   │   Mistral (Ollama)  │
│                     │   │                     │
│  • Fetch PR details │   │  • Receive diff     │
│  • Get file diffs   │   │  • Review code      │
│  • Post review      │   │  • Return feedback  │
└─────────────────────┘   └─────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     AZURE DEVOPS PR                             │
│              Structured review comment posted 🎯                │
└─────────────────────────────────────────────────────────────────┘
```

---

# High-Level Architecture

Workflow

Developer creates PR in Azure DevOps
A Service Hook / Pipeline Trigger fires
A small AI Reviewer Service runs
It:
Fetches PR diff
Sends diff to Mistral AI
Gets review suggestions

Posts comments back to the PR 
Focus on:
- bugs
- security vulnerabilities
- performance
- missing tests
- architecture issues

# Cost Optimization

Strategies:

Only review changed files

Skip large files (>1000 lines)

Skip generated files

# Table of Contents

## ✨ Features

- **Trigger on demand** — comment `@ai-reviewer` on any PR
- **Configurable context** — `@ai-reviewer 10` shows 10 lines of context around each change
- **Diff only mode** — `@ai-reviewer 0` reviews only changed lines
- **Structured reviews** — consistent format with Summary, Issues, Suggestions, Security checklist
- **Duplicate prevention** — threading + deduplication prevents multiple reviews
- **Local AI** — Mistral runs on your own machine via Ollama. No API costs. Full privacy.
- **Enterprise ready** — works on internal networks with no public internet required

## 🛠️ Tech Stack

| Technology | Purpose |
|-----------|---------|
| Python 3.11+ | Core application |
| Flask | Webhook server |
| Azure DevOps REST API | Fetch PR diffs, post comments |
| Mistral 7B (via Ollama) | AI code review |
| difflib | Generate unified diffs |
| threading | Async review processing |

---

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- [Ollama](https://ollama.com) installed and running
- Azure DevOps account with a repository
- Azure DevOps PAT token with Code (Read + Write) permissions

### 1. Clone the repo

```bash
git clone https://github.com/Deepti63/AI-PR-Reviewer.git
cd AI-PR-Reviewer
```

### 2. Set up virtual environment

```bash
python -m venv env
env\Scripts\activate        # Windows
source env/bin/activate     # Mac/Linux
pip install -r requirements.txt


### 3. Pull Mistral

```bash
ollama pull mistral
```

### 4. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your values:

```bash
AZURE_DEVOPS_ORG_URL=https://dev.azure.com/your-org
AZURE_DEVOPS_PROJECT=your-project
AZURE_DEVOPS_REPO=your-repo
AZURE_DEVOPS_PAT=your-pat-token
MISTRAL_API_URL=http://localhost:11434/api/generate
MISTRAL_MODEL=mistral
DIFF_CONTEXT_LINES=3
WEBHOOK_SECRET=your-random-secret
```

### 5. Start the server

```bash
python main.py
```

### 6. Expose with ngrok (for testing)

```bash
ngrok http 5000
```

### 7. Configure Azure DevOps Webhook

1. Go to `https://dev.azure.com/{org}/{project}/_settings/serviceHooks`
2. Create subscription → **Web Hooks**
3. Event: **Pull request commented on**
4. URL: `https://your-ngrok-url.ngrok-free.app/webhook`
5. Save

### 8. Trigger a review

Comment `@ai-reviewer` on any PR. Review appears in 30-60 seconds.


## 🗺️ Roadmap

- [x] Basic PR review on trigger comment
- [x] Configurable diff context lines via comment (`@ai-reviewer 10`)
- [x] Duplicate review prevention
- [x] Background processing (no webhook timeouts)
- [ ] Support multiple AI models (CodeLlama, LLaMA3)
- [ ] Inline comments on specific lines
- [ ] PR approval/rejection based on review score
- [ ] Metrics dashboard
- [ ] Docker deployment

## 🧠 What I Learned Building This

This project was built as a learning exercise covering:

- Python OOP — classes, dataclasses, type hints
- REST API integration — Azure DevOps, Ollama
- Webhook architecture — Flask, threading, deduplication
- Prompt engineering — structured AI outputs
- Git best practices — conventional commits, feature branches
- DevOps thinking — config management, fail-fast validation

## 👩‍💻 Author

**Deepti Sinha** — Enjoying the journey of building AI-powered DevOps tooling

## Output  generated automatically
<img width="992" height="907" alt="image" src="https://github.com/user-attachments/assets/a2043ca8-c031-4509-9178-11165acaaecc" />


