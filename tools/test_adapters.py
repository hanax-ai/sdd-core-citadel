#!/usr/bin/env python3
"""
Test script for Amigo Agents Task 2 Tool Adapters
"""

from pathlib import Path
import sys

# Add parent directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.git_adapter import get_git_status
from tools.linter_adapter import validate_json_syntax


def main():
    target = Path("/mnt/c/Users/JarvisRichardson/Desktop/WiP/SDD-Core-Framework-Analysis")
    status = get_git_status(target)
    print("Git Status:", status)

    sample_json = Path("/mnt/c/Users/JarvisRichardson/Desktop/SDD/Amigos-Agents/agents/builder.json")
    sample_json.parent.mkdir(parents=True, exist_ok=True)
    sample_json.write_text('{"name": "Amigo-Builder"}', encoding="utf-8")
    
    valid, msg = validate_json_syntax(sample_json)
    print("JSON Syntax Check:", valid, msg)


if __name__ == "__main__":
    main()
