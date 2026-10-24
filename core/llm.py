import json
import urllib.request
import urllib.error
from . import config
from .parser import clean_title, clean_description, parse_commit_message


def get_base_url(url: str = None) -> str:
    """Extract http://host:port from full generate URL."""
    target = url or config.OLLAMA_URL
    return target.split("/api/")[0]


def check_ollama() -> None:
    """Quick connectivity check — raises RuntimeError if Ollama isn't reachable."""
    base = get_base_url()
    try:
        urllib.request.urlopen(base, timeout=4)
    except urllib.error.URLError:
        raise RuntimeError(
            "Cannot reach Ollama at: " + base + "\n"
            "Make sure Ollama is running:  ollama serve"
        )


def get_installed_models(base_url: str = None) -> list:
    """Query Ollama API for installed models."""
    base = get_base_url(base_url)
    try:
        req = urllib.request.Request(f"{base}/api/tags")
        with urllib.request.urlopen(req, timeout=4) as response:
            data = json.loads(response.read().decode("utf-8"))
            models = []
            for m in data.get("models", []):
                name = m.get("name", "")
                if "embed" in name.lower():
                    continue
                size_gb = m.get("size", 0) / (1024 ** 3)
                models.append({"name": name, "size_gb": size_gb})
            return models
    except Exception:
        return []


def pull_model(model_name: str, base_url: str = None) -> bool:
    """Pull model from Ollama library with live progress output."""
    base = get_base_url(base_url)
    url = f"{base}/api/pull"
    payload = json.dumps({"name": model_name, "stream": True}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")

    print(f"\n  Connecting to Ollama to download '{model_name}'...")
    try:
        with urllib.request.urlopen(req, timeout=3600) as response:
            for line in response:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line.decode("utf-8"))
                    status = data.get("status", "")
                    completed = data.get("completed", 0)
                    total = data.get("total", 0)
                    if total > 0:
                        pct = (completed / total) * 100
                        comp_mb = completed / (1024 * 1024)
                        tot_mb = total / (1024 * 1024)
                        bar_len = 20
                        filled = int(bar_len * completed // total)
                        bar = "=" * filled + "-" * (bar_len - filled)
                        print(f"\r  [{bar}] {pct:5.1f}% | {comp_mb:5.0f}/{tot_mb:5.0f} MB | {status:<20}", end="", flush=True)
                    else:
                        print(f"\r  {status:<55}", end="", flush=True)
                except Exception:
                    pass
        print(f"\n  [+] Successfully downloaded '{model_name}'!")
        return True
    except Exception as e:
        print(f"\n  [!] Failed to pull model: {e}")
        return False

def ask_ollama(prompt, system="", max_tokens=100, temperature=0.1, _retry=True):
    payload = {
        "model": config.MODEL,
        "prompt": prompt,
        "stream": False,
        "keep_alive": config.KEEP_ALIVE,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens
        }
    }

    if system:
        payload["system"] = system

    request = urllib.request.Request(
        config.OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_msg = ""
        try:
            body = json.loads(e.read().decode("utf-8"))
            err_msg = body.get("error", "")
        except Exception:
            pass
        if not err_msg:
            err_msg = str(e)
        raise RuntimeError(f"Ollama server error ({e.code}): {err_msg}") from e
    except urllib.error.URLError as e:
        if _retry:
            print("\r  Request timed out — retrying once...", flush=True)
            return ask_ollama(prompt, system, max_tokens, temperature=temperature, _retry=False)
        raise RuntimeError(
            f"Could not connect to Ollama at: {config.OLLAMA_URL}\n"
            "Make sure Ollama is running:  ollama serve"
        ) from e

    answer = result.get("response", "").strip()

    if not answer:
        raise RuntimeError("Ollama returned an empty response.")

    return answer

def summarize_diff_chunk(chunk):
    prompt = f"""You are a master programmer analyzing a portion of a Git diff.

DIFF CHUNK:
{chunk}

---
Analyze the changes in this chunk.
Respond with 1 to 3 concise bullet points summarizing the technical changes.
Focus on WHAT changed and WHY.
Do NOT output markdown wrappers, just the bullet points starting with "- ".
"""
    return ask_ollama(prompt, max_tokens=150)

def generate_title(diff, feedback=None, temperature=0.1):
    feedback_block = ""
    if feedback:
        feedback_block = f"""
USER FEEDBACK / INSTRUCTIONS (HIGH PRIORITY):
{feedback}
Ensure the commit title directly addresses and incorporates this feedback.
"""

    prompt = f"""You are a master programmer writing Git commit messages.

INPUT (STAGED DIFF OR MAP-REDUCE SUMMARIES):
{diff}
{feedback_block}
---
Based on the input above, generate ONE Git commit title using Conventional Commits.
Respond with ONLY the plain text title. Do not include explanations, markdown formatting, or JSON.

OVERALL PURPOSE SYNTHESIS:
Before generating the title, identify the major logical changes, group them into functional areas, and determine which functional area represents the primary purpose of the overall change.
The title must describe this PRIMARY logical purpose of the ENTIRE staged change.

Do NOT simply choose the largest number of changed lines.
Do NOT choose the first or most obvious change.
Do NOT focus on a single component, page, file, API route, or database table when several changes collectively implement a larger capability.
If the input is a list of summaries, synthesize the overall change from them rather than focusing on one chunk.

Format: <type>: <short description>  OR  <type>(<scope>): <short description>

Type Selection:
feat     → introduces meaningful new functionality or capability
fix      → fixes incorrect existing behavior
refactor → restructures existing code without primarily adding functionality
perf     → primarily improves performance
docs     → documentation changes
test     → tests
chore    → maintenance/tooling/dependency work
build    → build system changes
ci       → CI/CD changes
(Do NOT automatically use "feat" for large changes).

Scope Rules (CRITICAL):
- Scope is completely OPTIONAL. When in doubt or when multiple files across different areas are touched, OMIT the scope entirely (e.g. "feat: add commit preview").
- If used, scope MUST be a single short noun representing a module or component (max 10 chars, e.g. "cli", "auth", "parser", "config", "ui").
- NEVER list filenames, file paths, extensions (e.g. NEVER ".py", ".sh"), or comma-separated lists in the scope.
- NEVER write scopes like "(commit.py, config.py)" or "(core/ui.py)".

Title Rules (STRICT LENGTH: 45 to 65 CHARACTERS):
- Strict limit: Under 70 characters total. Keep concise and punchy.
- Focus on the SINGLE primary action. Do NOT chain multiple actions with "and" (e.g. "enhance commit message generation", NOT "refactor and enhance commit message generation and configuration handling").
- One line only. Strictly complete sentence or phrase. NEVER cut off mid-sentence.
- Use imperative/present-tense wording (e.g. 'add', 'fix', 'simplify').
- Do not capitalize the first letter after the colon unless it is a proper noun or acronym.
- Do not end with a period.

Examples:
feat: add interactive settings menu
feat(cli): add memory cache configuration
fix(parser): handle markdown bold formatting in titles
refactor(llm): simplify single-pass commit generation
perf: optimize repository diff summarization
"""

    response = ask_ollama(prompt, max_tokens=120, temperature=temperature)
    return clean_title(response)

def generate_description(diff, title, feedback=None, temperature=0.1):
    feedback_block = ""
    if feedback:
        feedback_block = f"""
USER FEEDBACK / INSTRUCTIONS (HIGH PRIORITY):
{feedback}
Ensure the commit description directly addresses and incorporates this feedback.
"""

    prompt = f"""You are a master programmer writing Git commit messages.

INPUT (STAGED DIFF OR MAP-REDUCE SUMMARIES):
{diff}
{feedback_block}
---
The commit title is already decided as: {title}

Write a structured Git commit description. Respond with ONLY the plain text description. Do not include explanations or JSON.

SEMANTIC GROUPING REQUIREMENTS:
You must perform SEMANTIC GROUPING on the input material. Do NOT blindly list every change or chunk.
- Identify related changes and mentally group them into high-level functional areas.
- Multiple components implementing the same feature = ONE bullet.
- Multiple API, service, authorization, and DB changes supporting the same feature = ONE bullet.
- Do not create a separate bullet for every component, file, function, API route, or table.
- Describe the new capability rather than listing its implementation pieces.
- Ignore minor implementation details unless they are critical.
- Never exceed 5 bullets total (1-2 for small changes, 3-5 for complex changes).

DESCRIPTION STRUCTURE:
<One short paragraph describing the overall purpose of the change.>

- <High-level logical change>
- <High-level logical change>

Rules for Opening Paragraph:
- Summarize the overall purpose in 1-2 sentences.
- Do not simply repeat the commit title.
- Do not list individual files.
- Avoid vague phrases ("modernize", "improve code quality", "reduce complexity") unless clearly supported.

Rules for Bullets:
- Describe logical features or architectural changes.
- Group related implementation changes.
- Be specific and concrete.
- Do not invent motivation.
- Do not repeat the opening paragraph or title.
- Do not mention AI or write "This commit/change...".
- Use Markdown bullets exactly with "- ".
- Maximum 5 bullets.

Example Output:
Expand the role management flow with member and permission management.

- Add role member editing and management capabilities.
- Improve permission management with searchable permissions and clearing controls.
- Update authorization and role-management infrastructure to support organization-level permissions.
- Simplify the roles loading state and page routing.
"""

    response = ask_ollama(prompt, max_tokens=450, temperature=temperature)
    return clean_description(response)

def generate_commit_message(diff, feedback=None, temperature=0.1, custom_rules=None):
    """Generate both commit title and description in a single unified LLM pass for maximum speed."""
    feedback_block = ""
    if feedback:
        feedback_block = f"""
USER FEEDBACK / INSTRUCTIONS (HIGH PRIORITY):
{feedback}
Strictly incorporate this feedback into the title and description.
"""

    rules_block = ""
    if custom_rules:
        rules_block = f"""
REPOSITORY COMMIT RULES (STRICTLY ENFORCE):
{custom_rules}
"""

    prompt = f"""You are a master programmer writing Git commit messages.

INPUT (STAGED DIFF OR MAP-REDUCE SUMMARIES):
{diff}
{rules_block}
{feedback_block}
---
Based on the input above, generate a complete Conventional Commit message.

OUTPUT STRUCTURE:
<type>: <short description>  (or <type>(<scope>): <short description>)

<1-2 sentence paragraph describing the overall purpose.>

- <High-level logical change 1>
- <High-level logical change 2>

RULES:
1. Title (Line 1):
- Format: <type>: <short description>  OR  <type>(<scope>): <short description>
- Allowed Types: feat, fix, refactor, perf, docs, test, chore, build, ci
- Scope Rules:
  * Scope is OPTIONAL. If changes span multiple areas or files, OMIT the scope entirely (e.g. 'feat: add commit preview').
  * If used, scope MUST be a single short noun representing a module (max 10 chars, e.g. 'cli', 'config', 'parser', 'ui').
  * NEVER list filenames, paths, file extensions (e.g. NEVER '.py', '.sh'), or comma-separated lists in the scope.
- Strict length limit: Keep between 45 and 65 characters. NEVER exceed 70 characters.
- Focus on ONE primary action. Do NOT chain multiple verbs with 'and'.
- MUST be a complete sentence or phrase. NEVER cut off mid-sentence.
- Use imperative, present-tense wording (e.g., 'add', 'fix', not 'added', 'fixes').
- Start description with lowercase unless it is an acronym or proper noun.
- Do not end the title with a period.

2. Blank Line:
- Leave exactly one blank line after the title.

3. Description Body:
- Start with 1-2 sentences summarizing the overall purpose (why the change was made).
- Follow with 1 to 5 high-level grouped bullet points starting with '- '.
- Group related file changes together; do NOT list every changed file or detail.
- Do NOT mention AI or write 'This commit...'.
- Output ONLY plain text without markdown wrappers or code fences.
"""

    response = ask_ollama(prompt, max_tokens=500, temperature=temperature)
    return parse_commit_message(response)

