import json
import re

NOISE_FILES = (
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", 
    "poetry.lock", "Cargo.lock", "Gemfile.lock", "bun.lockb", "composer.lock",
    ".svg", ".min.js", ".min.css", ".map"
)

def split_diff_by_file(raw_diff):
    # Splits the diff by 'diff --git a/' which is the start of every file's diff
    parts = re.split(r'(^diff --git a/)', raw_diff, flags=re.MULTILINE)
    
    if len(parts) < 2:
        return [raw_diff]
        
    file_diffs = []
    # parts[0] is usually preamble/empty. Combine delimiter and actual content.
    for i in range(1, len(parts), 2):
        file_diffs.append(parts[i] + parts[i+1])
        
    return file_diffs

def filter_noise_files(file_diffs):
    filtered = []
    for diff in file_diffs:
        first_line = diff.splitlines()[0] if diff else ""
        
        is_noise = False
        for noise in NOISE_FILES:
            if noise in first_line:
                is_noise = True
                break
                
        if is_noise:
            # Keep just the header so the model knows it changed
            header = "\n".join(diff.splitlines()[:2])
            filtered.append(header + "\n(File content excluded from summary due to auto-generation noise)\n")
        else:
            filtered.append(diff)
            
    return filtered

def batch_file_diffs(file_diffs, max_chars):
    batches = []
    current_batch = []
    current_len = 0
    
    for diff in file_diffs:
        diff_len = len(diff)
        
        # If a single file diff is larger than max_chars, it must be truncated
        if diff_len > max_chars:
            if current_batch:
                batches.append("".join(current_batch))
                current_batch = []
                current_len = 0
                
            truncated = diff[:max_chars]
            last_nl = truncated.rfind("\n")
            if last_nl != -1:
                truncated = truncated[:last_nl]
            truncated += "\n... [FILE DIFF TRUNCATED DUE TO EXTREME LENGTH] ...\n"
            batches.append(truncated)
            continue
            
        if current_len + diff_len > max_chars:
            batches.append("".join(current_batch))
            current_batch = [diff]
            current_len = diff_len
        else:
            current_batch.append(diff)
            current_len += diff_len
            
    if current_batch:
        batches.append("".join(current_batch))
        
    return batches

def clean_desc_case(desc: str) -> str:
    """Ensure the description starts with lowercase unless it is an acronym or proper noun."""
    if not desc:
        return ""
    first_word = desc.split()[0]
    if first_word.isupper() or first_word in ("Git", "Ollama", "Python", "Linux", "Windows", "CLI", "API", "URL", "JSON"):
        return desc
    return desc[0].lower() + desc[1:]


def sanitize_title_scope(title: str) -> str:
    """Sanitize bloated scopes (e.g. multiple comma-separated files or file extensions)."""
    m = re.match(r"^([a-z]+)\s*\(([^)]+)\)\s*:\s*(.*)$", title, re.IGNORECASE)
    if not m:
        return title

    ctype = m.group(1).lower()
    raw_scope = m.group(2).strip()
    desc = clean_desc_case(m.group(3).strip())

    # If scope contains commas, spaces, slashes, or extensions, it is a file list or invalid
    if any(sep in raw_scope for sep in (",", ";", "/", "\\", " ")):
        return f"{ctype}: {desc}"

    # Strip common file extensions if single file name provided, e.g. (commit.py) -> (commit)
    clean_scope = re.sub(r"\.[a-zA-Z0-9]+$", "", raw_scope).strip().lower()

    # Scope must be a clean short identifier (2 to 12 alphanumeric/dash chars)
    if re.match(r"^[a-z0-9_-]{2,12}$", clean_scope):
        return f"{ctype}({clean_scope}): {desc}"

    return f"{ctype}: {desc}"


def truncate_title(title: str, max_len: int = 70) -> str:
    """Intelligently shorten long titles at clean word boundaries or compound clauses."""
    if len(title) <= max_len:
        return title

    # Look for compound conjunctions or commas to split into a complete single clause
    for delim in (" and ", " with ", ", "):
        pos = title.rfind(delim)
        while pos > 28:
            candidate = title[:pos].rstrip(" ,-:")
            if len(candidate) <= max_len:
                return candidate
            pos = title.rfind(delim, 0, pos)

    # Otherwise cut at word boundary before max_len
    sub = title[:max_len]
    last_space = sub.rfind(" ")
    if last_space > 25:
        sub = sub[:last_space]

    for trailing in (" and", " with", " for", " to", " of", " in", " on", " by", ",", "-", ":", ";", "."):
        if sub.endswith(trailing):
            sub = sub[:-len(trailing)].strip()

    return sub


def clean_title_line(line: str) -> str:
    """Strip markdown formatting, bold, headers, bullets, and title prefixes."""
    line = line.strip()
    if not line:
        return ""

    # Remove code blocks and inline backticks
    line = line.replace("```", "").replace("`", "").strip()

    # Remove bold and italic markers completely from title
    line = line.replace("**", "").replace("__", "").strip()

    # Strip markdown headers (#, ##, etc.)
    line = re.sub(r"^#+\s*", "", line).strip()

    # Strip leading bullet/list markers (e.g. '- ', '* ', '1. ')
    line = re.sub(r"^(\*|-|\d+\.)\s+", "", line).strip()

    # Strip common title prefixes
    prefixes = (
        "commit title:", "title:", "commit message:", "commit:", "subject:", "summary:"
    )
    for p in prefixes:
        if line.lower().startswith(p):
            line = line[len(p):].strip()

    # Strip accidental surrounding quotes
    if len(line) >= 2 and line[0] == line[-1] and line[0] in ('"', "'"):
        line = line[1:-1].strip()

    # Clean any trailing punctuation, asterisks, or whitespace
    cleaned = line.strip("*_` ").rstrip(".").strip()

    # Sanitize bloated scope
    cleaned = sanitize_title_scope(cleaned)

    # Format description case after colon
    colon_idx = cleaned.find(":")
    if colon_idx != -1:
        prefix = cleaned[:colon_idx + 1]
        desc = cleaned[colon_idx + 1:].strip()
        cleaned = f"{prefix} {clean_desc_case(desc)}"

    # Ensure title fits within recommended length
    cleaned = truncate_title(cleaned)

    return cleaned


def clean_title(response):
    """
    Extract a usable commit title from the model response.
    """
    # Attempt to parse as JSON in case the model ignored instructions
    clean_resp = response.strip()
    if clean_resp.startswith("```json"):
        clean_resp = clean_resp[7:].strip()
    if clean_resp.endswith("```"):
        clean_resp = clean_resp[:-3].strip()

    try:
        parsed = json.loads(clean_resp)
        if isinstance(parsed, dict):
            if "title" in parsed:
                response = parsed["title"]
            elif "response" in parsed:
                response = parsed["response"]
    except Exception:
        pass

    allowed_types = (
        "feat:", "feat(", "fix:", "fix(", "refactor:", "refactor(",
        "perf:", "perf(", "docs:", "docs(", "test:", "test(",
        "chore:", "chore(", "build:", "build(", "ci:", "ci("
    )

    first_candidate = ""

    for line in response.splitlines():
        candidate = clean_title_line(line)
        if not candidate:
            continue

        if not first_candidate:
            first_candidate = candidate

        lower = candidate.lower()
        if any(lower.startswith(t) for t in allowed_types):
            return candidate

    # Fallback to first non-empty line if no explicit conventional prefix was found
    if first_candidate:
        return first_candidate

    raise RuntimeError(
        "The model generated an empty commit title.\n\n"
        f"Model response:\n{response}"
    )

def clean_description(response):
    """
    Clean the model's description.
    """
    # Attempt to parse as JSON in case the model ignored instructions
    clean_resp = response.strip()
    if clean_resp.startswith("```json"):
        clean_resp = clean_resp[7:].strip()
    if clean_resp.endswith("```"):
        clean_resp = clean_resp[:-3].strip()

    try:
        parsed = json.loads(clean_resp)
        if isinstance(parsed, dict):
            if "description" in parsed:
                response = parsed["description"]
            elif "response" in parsed:
                response = parsed["response"]
    except Exception:
        pass

    lines = []

    for line in response.splitlines():
        clean_line = line.strip()

        clean_line = clean_line.replace("```", "")

        if clean_line.lower().startswith("description:"):
            clean_line = clean_line[12:].strip()

        lines.append(clean_line)

    if not any(lines):
        raise RuntimeError(
            "The model did not generate a description."
        )

    # Rejoin with newlines but clean up excessive empty lines
    joined = "\n".join(lines).strip()
    joined = re.sub(r'\n{3,}', '\n\n', joined)
    
    return joined

def parse_commit_message(response):
    """
    Parse a unified commit message string from the LLM into (title, description).
    """
    clean_resp = response.strip()
    if not clean_resp:
        raise RuntimeError("The model returned an empty commit message.")
    if clean_resp.startswith("```"):
        lines = clean_resp.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        clean_resp = "\n".join(lines).strip()

    try:
        parsed = json.loads(clean_resp)
        if isinstance(parsed, dict) and "title" in parsed:
            return clean_title(parsed["title"]), clean_description(parsed.get("description", ""))
    except Exception:
        pass

    allowed_types = (
        "feat:", "feat(", "fix:", "fix(", "refactor:", "refactor(",
        "perf:", "perf(", "docs:", "docs(", "test:", "test(",
        "chore:", "chore(", "build:", "build(", "ci:", "ci("
    )

    lines = clean_resp.splitlines()
    title_idx = -1
    title = ""

    for i, line in enumerate(lines):
        candidate = clean_title_line(line)
        if not candidate:
            continue
        lower = candidate.lower()
        if any(lower.startswith(t) for t in allowed_types):
            title_idx = i
            title = candidate
            break

    if title_idx == -1 and lines:
        for i, line in enumerate(lines):
            candidate = clean_title_line(line)
            if candidate:
                title_idx = i
                title = candidate
                break

    desc_lines = lines[title_idx + 1:] if title_idx != -1 else []
    while desc_lines and not desc_lines[0].strip():
        desc_lines.pop(0)

    desc_text = "\n".join(desc_lines).strip()
    try:
        description = clean_description(desc_text) if desc_text else f"- {title}"
    except RuntimeError:
        description = f"- {title}"

    return title, description
