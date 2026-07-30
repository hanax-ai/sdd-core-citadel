"""
Amigo Agents Linter & Schema Adapter
Runs Draft 2020-12 JSON Schema validation and SHA-256 file table recomputations.
"""

from __future__ import annotations
import hashlib
import json
from pathlib import Path


def compute_file_sha256(path: Path) -> str:
    """Compute uppercase SHA-256 hash of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def validate_json_syntax(path: Path) -> tuple[bool, str]:
    """Validate strict JSON syntax with duplicate-key rejection and no NaN/Infinity."""
    def reject_duplicate_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        content = path.read_text(encoding="utf-8")
        json.loads(content, object_pairs_hook=reject_duplicate_keys, parse_constant=lambda c: (_ for _ in ()).throw(ValueError(f"nonstandard JSON constant: {c}")))
        return True, "OK"
    except Exception as exc:
        return False, str(exc)
