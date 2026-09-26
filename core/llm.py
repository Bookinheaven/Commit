import json
import urllib.request
import urllib.error
from . import config
from .parser import clean_title, clean_description

def ask_ollama(prompt, system="", max_tokens=100):
    payload = {
        "model": config.MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
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
    except urllib.error.URLError as e:
        raise RuntimeError(
            "Could not connect to Ollama.\n"
            "Make sure Ollama is running."
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

def generate_title(diff):
    prompt = f"""You are a master programmer writing Git commit messages.

INPUT (STAGED DIFF OR MAP-REDUCE SUMMARIES):
{diff}

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

Format: <type>(<scope>): <short description>

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

Rules:
- Maximum 72 characters.
- One line only.
- Use imperative/present-tense wording.
- Be specific enough to distinguish the commit from a generic "update" or "refactor".
- Do not include secondary implementation details.
- Avoid vague words ("update", "improve", "modernize", "cleanup") when a more specific description is possible.

Examples:
feat(auth): add session-based authentication
fix(api): handle invalid request payloads
feat(roles): expand role and permission management
refactor(db): simplify organization permission queries
perf(search): optimize repository file indexing
"""

    response = ask_ollama(prompt, max_tokens=50)
    return clean_title(response)

def generate_description(diff, title):
    prompt = f"""You are a master programmer writing Git commit messages.

INPUT (STAGED DIFF OR MAP-REDUCE SUMMARIES):
{diff}

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

    response = ask_ollama(prompt, max_tokens=250)
    return clean_description(response)
