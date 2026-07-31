#!/usr/bin/env python3
"""
Amigo Agents Harness CLI Runner
Orchestrates the Researcher/Builder/Gatekeeper collaboration cycle for
a target directory and task.
"""

from __future__ import annotations
import argparse
import asyncio
import sys
from pathlib import Path

# Add parent directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Force UTF-8 stdout so emoji output doesn't crash on default Windows consoles (cp1252).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from harness.config import AMIGO_ROOT, DEFAULT_TARGET_DIR, ensure_directories, get_env_summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Amigo Agents — Multi-Agent Builder & Gatekeeper Review Harness",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--task",
        type=str,
        help="Task description or goal statement for Amigo Agents",
    )
    parser.add_argument(
        "--target-dir",
        type=str,
        default=str(DEFAULT_TARGET_DIR),
        help="Target codebase directory to audit / build against",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Display Amigo Agents environment status and exit",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    ensure_directories()
    args = parse_args(argv)

    if args.status:
        summary = get_env_summary()
        print("=== 🤝 Amigo Agents Environment Status ===")
        print(f"Amigo Root:    {summary['amigo_root']}")
        print(f"Default Target:{summary['default_target']}")
        print(f"Anthropic Key: {'SET' if summary['anthropic_key_set'] else 'NOT SET'}")
        print(f"OpenAI Key:    {'SET' if summary['openai_key_set'] else 'NOT SET'}")
        # Only the ACTIVE Gatekeeper provider's key is reported. Printing
        # "Gemini Key: NOT SET" on a working Kimi config is a false alarm, and
        # never mentioning MOONSHOT_API_KEY at all is a false all-clear that
        # lets a run die mid-Gatekeeper. Mirrors /api/system/status.
        provider = summary["gatekeeper_provider"]
        if provider is None:
            print("Gatekeeper:    UNRECOGNISED GATEKEEPER_PROVIDER")
            print("               valid values are 'gemini' (default) and 'kimi'; no run can start")
        elif provider == "kimi":
            print("Gatekeeper:    kimi (MOONSHOT_API_KEY)")
            print(f"Moonshot Key:  {'SET' if summary['moonshot_key_set'] else 'NOT SET'}")
        else:
            print("Gatekeeper:    gemini (GEMINI_API_KEY)")
            print(f"Gemini Key:    {'SET' if summary['gemini_key_set'] else 'NOT SET'}")
        return 0

    if not args.task:
        print("🤝 Amigo Agents Harness Runner v0.1.0")
        print("Use --help for options or --status to view environment status.")
        return 0

    print(f"🚀 Initializing Amigo Agents for task: {args.task}")
    print(f"📂 Target Directory: {args.target_dir}")
    
    target_path = Path(args.target_dir)
    from harness.remediation_loop import run_collaboration_cycle
    result = asyncio.run(run_collaboration_cycle(target_path, args.task))

    print(f"\n✨ Amigo Agents Collaboration Cycle Complete! Verdict: {result['verdict']}")
    print(f"📄 Transcript: {result['log_path']}")
    print(f"\n--- Proposed Patch ---\n{result['patch_text']}")
    return 0



if __name__ == "__main__":
    sys.exit(main())
