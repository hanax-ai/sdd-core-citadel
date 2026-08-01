"""
Amigo Agents Config Manager
Handles workspace paths, environment bindings, and log destinations.
"""

from pathlib import Path
import os

# Root directory of Amigo Agents
AMIGO_ROOT = Path(__file__).resolve().parents[1]

def load_env_file():
    """Load environment variables from .env file if present."""
    env_file = AMIGO_ROOT / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip().strip("'\""))

load_env_file()

def resolve_default_target_dir() -> Path:
    """Directory the harness audits / builds against by default.

    Honours AMIGO_TARGET_DIR, which harness/bridge.py already reads -- this just
    applies it at the source rather than only at the bridge. Empty or
    whitespace-only counts as unset, matching resolve_gatekeeper_provider.

    Falls back to the repo itself. This used to be a hardcoded absolute path to
    one developer's machine, which meant tests asserting the directory exists
    failed on every other machine and made CI impossible to run at all. The repo
    root always exists in any clone, so the default is portable.
    """
    configured = os.environ.get("AMIGO_TARGET_DIR", "").strip()
    return Path(configured).resolve() if configured else AMIGO_ROOT


DEFAULT_TARGET_DIR = resolve_default_target_dir()

# Sub-directories
HARNESS_DIR = AMIGO_ROOT / "harness"
AGENTS_DIR = AMIGO_ROOT / "agents"
TOOLS_DIR = AMIGO_ROOT / "tools"
LOGS_DIR = AMIGO_ROOT / "logs"

def ensure_directories():
    """Ensure all required runtime directories exist."""
    for d in [HARNESS_DIR, AGENTS_DIR, TOOLS_DIR, LOGS_DIR]:
        d.mkdir(parents=True, exist_ok=True)

# The API key each Gatekeeper provider needs. Doubles as the set of valid
# GATEKEEPER_PROVIDER values, so a provider can never be accepted without a key
# to check for it.
GATEKEEPER_KEY_ENV = {
    "gemini": "GEMINI_API_KEY",
    "kimi": "MOONSHOT_API_KEY",
}

def resolve_gatekeeper_provider() -> str:
    """Return the provider the Gatekeeper is currently configured to use.

    Mirrors the routing in harness.llm_clients.call_gatekeeper exactly --
    including the empty/whitespace-means-unset rule and the error text -- so a
    health probe cannot report a different provider than the one a run would
    actually call. Read live rather than cached at import time, because
    call_gatekeeper reads it live too. tests/test_bridge.py pins the two
    implementations together so they cannot drift silently.
    """
    provider = os.getenv("GATEKEEPER_PROVIDER", "").strip().lower() or "gemini"
    if provider not in GATEKEEPER_KEY_ENV:
        raise RuntimeError(
            f"GATEKEEPER_PROVIDER is set to {provider!r}; valid values are 'gemini' (default) and 'kimi'."
        )
    return provider

def get_env_summary() -> dict:
    """Return summary of current environment keys and tool availability."""
    try:
        gatekeeper_provider = resolve_gatekeeper_provider()
    except RuntimeError:
        # An unrecognised GATEKEEPER_PROVIDER means no provider will serve the
        # Gatekeeper at all; report that as "unknown" rather than crashing the
        # status summary that exists to explain misconfiguration.
        gatekeeper_provider = None
    return {
        "anthropic_key_set": bool(os.getenv("ANTHROPIC_API_KEY")),
        "gemini_key_set": bool(os.getenv("GEMINI_API_KEY")),
        "moonshot_key_set": bool(os.getenv("MOONSHOT_API_KEY")),
        "openai_key_set": bool(os.getenv("OPENAI_API_KEY")),
        "gatekeeper_provider": gatekeeper_provider,
        "amigo_root": str(AMIGO_ROOT),
        "default_target": str(DEFAULT_TARGET_DIR),
    }
