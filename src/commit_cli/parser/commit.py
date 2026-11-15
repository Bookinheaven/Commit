"""Parser and validator for structured Conventional Commit messages."""

import json
import re
from typing import Any

from commit_cli.exceptions import CommitParseError, CommitValidationError
from commit_cli.models import CommitMessage, CommitType

VALID_SCOPE_PATTERN = re.compile(r"^[a-zA-Z0-9_/@.-]+$")
CONVENTIONAL_TITLE_PATTERN = re.compile(
    r"^([a-z]+)(?:\(([^)]+)\))?(!)?:\s*(.+)$", re.IGNORECASE
)

COMMIT_MESSAGE_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": {
            "type": "string",
            "enum": [t.value for t in CommitType],
        },
        "scope": {
            "type": ["string", "null"],
        },
        "subject": {
            "type": "string",
        },
        "body": {
            "type": ["string", "null"],
        },
        "breaking_change": {
            "type": ["string", "null"],
        },
    },
    "required": ["type", "subject"],
}


def validate_commit_message(msg: CommitMessage) -> None:
    """Validate that a CommitMessage complies with Conventional Commits rules.

    Raises:
        CommitValidationError: If any field fails validation.
    """
    # 1. Type validation
    if not isinstance(msg.type, CommitType):
        raise CommitValidationError(
            f"Invalid commit type '{msg.type}'. Allowed types are: {', '.join(t.value for t in CommitType)}"
        )

    # 2. Scope validation (optional, but must be well-formed if present)
    if msg.scope is not None:
        clean_scope = msg.scope.strip()
        if not clean_scope:
            raise CommitValidationError("Scope cannot be empty if specified.")
        if not VALID_SCOPE_PATTERN.match(clean_scope):
            raise CommitValidationError(
                f"Invalid scope '{clean_scope}'. Scopes must consist of alphanumeric characters, hyphens, underscores, slashes, or dots."
            )

    # 3. Subject validation (required)
    if not msg.subject or not msg.subject.strip():
        raise CommitValidationError("Commit subject cannot be empty.")

    clean_subject = msg.subject.strip()
    if len(clean_subject) > 100:
        raise CommitValidationError(
            f"Commit subject is too long ({len(clean_subject)} characters). Recommended max length is 72."
        )


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """Attempt to extract and parse a JSON object from text."""
    clean = text.strip()
    if clean.startswith("```"):
        lines = clean.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        clean = "\n".join(lines).strip()

    # Direct JSON parse (strict RFC 8259 compliance)
    try:
        data = json.loads(clean)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, TypeError):
        pass

    # Search for outermost JSON braces { ... }
    first_brace = clean.find("{")
    last_brace = clean.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidate = clean[first_brace : last_brace + 1]
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, TypeError):
            pass

    return None


def _parse_plaintext_fallback(text: str) -> CommitMessage | None:
    """Fallback parser for plaintext Conventional Commit messages.

    Preserves multiline body paragraphs and lines beginning with '#'.
    """
    raw_lines = text.strip().splitlines()
    if not raw_lines:
        return None

    # First non-empty line is the title
    idx = 0
    while idx < len(raw_lines) and not raw_lines[idx].strip():
        idx += 1
    if idx >= len(raw_lines):
        return None

    title_line = raw_lines[idx].strip()
    match = CONVENTIONAL_TITLE_PATTERN.match(title_line)
    if not match:
        return None

    type_str = match.group(1).lower()
    scope_str = match.group(2)
    is_breaking_bang = match.group(3) == "!"
    subject_str = match.group(4).strip().rstrip(".")

    try:
        ctype = CommitType(type_str)
    except ValueError:
        return None

    # Skip blank lines immediately after title
    idx += 1
    while idx < len(raw_lines) and not raw_lines[idx].strip():
        idx += 1

    body_lines: list[str] = []
    breaking_change_text: str | None = None

    while idx < len(raw_lines):
        line = raw_lines[idx]
        stripped = line.strip()
        if stripped.upper().startswith("BREAKING CHANGE:") or stripped.upper().startswith("BREAKING-CHANGE:"):
            bc_parts = [stripped.split(":", 1)[1].strip()]
            idx += 1
            while idx < len(raw_lines):
                bc_parts.append(raw_lines[idx].rstrip())
                idx += 1
            breaking_change_text = "\n".join(bc_parts).strip()
            break
        else:
            body_lines.append(line.rstrip())
            idx += 1

    if is_breaking_bang and not breaking_change_text:
        breaking_change_text = "Backwards-incompatible change."

    body_text = "\n".join(body_lines).strip() if body_lines else None

    return CommitMessage(
        type=ctype,
        subject=subject_str,
        scope=scope_str.strip() if scope_str else None,
        body=body_text,
        breaking_change=breaking_change_text,
    )


def parse_commit_response(response_text: str) -> CommitMessage:
    """Parse raw LLM response text into a validated CommitMessage model.

    Supports structured JSON responses and plaintext Conventional Commit fallbacks.

    Raises:
        CommitParseError: If response text cannot be parsed into commit structure.
        CommitValidationError: If parsed fields violate Conventional Commit rules.
    """
    if not response_text or not response_text.strip():
        raise CommitParseError("Received empty response from generation provider.")

    json_data = _extract_json_object(response_text)
    msg: CommitMessage | None = None

    if json_data:
        # 1. Type
        raw_type = str(json_data.get("type", "")).strip().lower()
        try:
            commit_type = CommitType(raw_type)
        except ValueError:
            raise CommitValidationError(
                f"Invalid commit type '{raw_type}'. Allowed types are: {', '.join(t.value for t in CommitType)}"
            )

        # 2. Scope
        raw_scope = json_data.get("scope")
        scope = str(raw_scope).strip() if raw_scope is not None and str(raw_scope).strip() else None

        # 3. Subject
        raw_subject = str(json_data.get("subject", "")).strip().rstrip(".")
        if not raw_subject:
            raise CommitValidationError("Commit subject cannot be empty.")

        # 4. Body
        raw_body = json_data.get("body")
        body = str(raw_body).strip() if raw_body is not None and str(raw_body).strip() else None

        # 5. Breaking change
        raw_bc = json_data.get("breaking_change")
        breaking_change = str(raw_bc).strip() if raw_bc is not None and str(raw_bc).strip() else None

        msg = CommitMessage(
            type=commit_type,
            scope=scope,
            subject=raw_subject,
            body=body,
            breaking_change=breaking_change,
        )
    else:
        # Fallback to plaintext Conventional Commit parser
        msg = _parse_plaintext_fallback(response_text)
        if msg is None:
            raise CommitParseError(
                f"Could not parse response into a Conventional Commit message.\nRaw response:\n{response_text}"
            )

    validate_commit_message(msg)
    return msg
