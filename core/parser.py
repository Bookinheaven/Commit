import json
import re

NOISE_FILES = (
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", 
    "poetry.lock", "Cargo.lock", "Gemfile.lock",
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

    for line in response.splitlines():
        line = line.strip()

        if not line:
            continue

        # Remove common Markdown formatting.
        line = line.replace("```", "")
        line = line.replace("`", "")

        if line.lower().startswith("title:"):
            line = line[6:].strip()

        # Remove accidental surrounding quotes.
        if len(line) >= 2 and line[0] == line[-1] and line[0] in ('"', "'"):
            line = line[1:-1].strip()

        lower_line = line.lower()
        if any(lower_line.startswith(t) for t in allowed_types):
            return line[:72]

    raise RuntimeError(
        "The model generated an invalid commit title.\n\n"
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
