# reviewer/prompt_builder.py
# ─────────────────────────────────────────────────────────────
# PURPOSE: Build the prompt we send to Mistral.
# The quality of the prompt determines the quality of the review.
# This is the most important file in the reviewer/ package.
# ─────────────────────────────────────────────────────────────

from azure_devops.models import PullRequest


class PromptBuilder:
    """
    Builds structured prompts for AI code review.

    🧠 CONCEPT: Prompt Engineering
    An LLM is only as good as the instructions you give it.
    A prompt has three parts:

    1. SYSTEM PROMPT — sets the AI's role and behaviour
       "You are an expert code reviewer..."
       This shapes HOW it thinks.

    2. CONTEXT — gives the AI the facts it needs
       PR title, author, files changed
       This is WHAT it knows.

    3. INSTRUCTION — tells the AI what to produce
       "Review the following diff and return..."
       This is WHAT it must do.

    Getting these three right = a genuinely useful review.
    """

    # 🧠 CONCEPT: Class-level constants
    # Defined at class level (not inside a method) so they are
    # shared across ALL instances. Only one copy in memory.
    # Access via self.SYSTEM_PROMPT or PromptBuilder.SYSTEM_PROMPT
    SYSTEM_PROMPT = """You are a senior software engineer and code reviewer with expertise in DevOps, security, and software quality.

Your job is to review pull request diffs and provide structured, actionable feedback.

RULES:
- Be specific — reference exact line numbers or code snippets when possible
- Be constructive — explain WHY something is an issue, not just WHAT
- Be concise — no filler, every sentence must add value
- Prioritise — lead with critical issues, end with minor suggestions
- Be honest — if the code is good, say so clearly

RESPONSE FORMAT — always use this exact structure:

## 📋 Summary
One paragraph describing what this PR does based on the diff.

## ✅ Strengths
- What the code does well (be specific)

## ⚠️ Issues Found
- **[CRITICAL]** Security vulnerabilities, data loss risks, breaking changes
- **[WARNING]** Bugs, logic errors, missing error handling
- **[STYLE]** Readability, naming, formatting issues
(Use "None found." if no issues exist at that severity level)

## 💡 Suggestions
- Specific actionable improvements with examples where possible

## 🔒 Security Checklist
- [ ] No hardcoded secrets or credentials
- [ ] Input validation is present where needed
- [ ] Error handling covers failure cases
- [ ] No sensitive data exposed in logs

## 📊 Overall Assessment
**Score: X/10** — one sentence verdict.
"""

    def build_review_prompt(self, pr: PullRequest) -> str:
        """
        Builds the full prompt to send to Mistral.

        🧠 CONCEPT: Separation of system vs user prompt
        system prompt = permanent instructions (role, format rules)
        user prompt   = changes per request (this specific PR's data)

        We keep them separate so:
        1. The system prompt is reusable across all PRs
        2. The user prompt is clean and focused on THIS PR only
        3. Ollama accepts them separately (system= and prompt= params)

        This method builds the USER prompt only.
        The system prompt is sent separately to Ollama.
        """

        # Build the context block — gives AI the PR overview
        context = self._build_context(pr)

        # Build the diff block — the actual code to review
        diff = self._build_diff_section(pr)

        # 🧠 CONCEPT: Multi-line f-string
        # Triple quotes let us write clean readable templates.
        # Variables are injected with {variable_name}.
        user_prompt = f"""Please review the following pull request.

{context}

{diff}

Provide your review following the exact format specified."""

        return user_prompt

    def _build_context(self, pr: PullRequest) -> str:
        """
        Builds the PR context block.
        Gives the AI metadata about the PR before showing the code.

        🧠 CONCEPT: Why context matters
        Without context, the AI reviews code in a vacuum.
        Knowing it's a Dockerfile change vs a payment module
        completely changes what issues are worth flagging.
        """
        return f"""### PR Context
- **Title:** {pr.title}
- **Author:** {pr.author}
- **Branch:** `{pr.source_branch}` → `{pr.target_branch}`
- **Files changed:** {len(pr.files)}
- **Description:** {pr.description or "No description provided."}"""

    def _build_diff_section(self, pr: PullRequest) -> str:
        """
        Builds the diff section of the prompt.

        🧠 CONCEPT: Token limits
        LLMs have a maximum input size (context window).
        Mistral 7B handles ~8000 tokens (~6000 words).
        A large PR could easily exceed this.

        Strategy:
        - Cap each file diff at MAX_DIFF_CHARS characters
        - Skip files with no diff
        - Add a warning if content was truncated

        This is called DEFENSIVE PROMPTING — always assume
        the input could be larger than expected.
        """
        MAX_DIFF_CHARS = 1500   # per file — keeps total prompt manageable

        sections = ["### Code Changes"]

        for f in pr.files:
            if not f.diff:
                continue

            # Warn the AI if we truncated — it should know
            # 🧠 CONCEPT: Ternary expression
            # a if condition else b — compact if/else on one line
            truncated = len(f.diff) > MAX_DIFF_CHARS
            diff_content = (
                f.diff[:MAX_DIFF_CHARS] + "\n... [truncated — file too large]"
                if truncated
                else f.diff
            )

            sections.append(
                f"#### `{f.filename}` ({f.change_type})\n"
                f"```diff\n{diff_content}\n```"
            )

        if len(sections) == 1:
            # Only the header — no actual diffs found
            sections.append("No diff content available for review.")

        return "\n\n".join(sections)

    def get_system_prompt(self) -> str:
        """Returns the system prompt for Ollama."""
        return self.SYSTEM_PROMPT


# ─────────────────────────────────────────────────────────────
# Quick test — see what prompt gets built for a fake PR
# python -m reviewer.prompt_builder
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from azure_devops.models import PullRequest, PRFile

    # Build a fake PR to test the prompt
    fake_pr = PullRequest(
        id=1,
        title="Updated Dockerfile",
        description="Added test comment and fixed Gemfile",
        author="Deepti Sinha",
        source_branch="testAiReviewer",
        target_branch="master",
        files=[
            PRFile(
                filename="/image/Dockerfile",
                change_type="edit",
                diff="[3 lines of context]\n--- before/Dockerfile\n+++ after/Dockerfile\n@@ -1,4 +1,5 @@\n # syntax=docker/dockerfile:1.4\n+#test\n ARG ARCH\n ARG NAME"
            ),
            PRFile(
                filename="/Gemfile",
                change_type="edit",
                diff="[3 lines of context]\n--- before/Gemfile\n+++ after/Gemfile\n@@ -3,3 +3,4 @@\n gem 'rspec-core'\n gem 'rspec-expectations'\n+gem 'rake'"
            ),
        ]
    )

    builder = PromptBuilder()
    prompt = builder.build_review_prompt(fake_pr)

    print("=" * 60)
    print("SYSTEM PROMPT:")
    print("=" * 60)
    print(builder.get_system_prompt())

    print("\n" + "=" * 60)
    print("USER PROMPT:")
    print("=" * 60)
    print(prompt)