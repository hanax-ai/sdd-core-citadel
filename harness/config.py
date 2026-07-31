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

# Default target directory to audit / build against
DEFAULT_TARGET_DIR = Path(r"C:\Users\JarvisRichardson\Desktop\WiP\SDD-Core-Framework-Analysis")

# Sub-directories
HARNESS_DIR = AMIGO_ROOT / "harness"
AGENTS_DIR = AMIGO_ROOT / "agents"
TOOLS_DIR = AMIGO_ROOT / "tools"
LOGS_DIR = AMIGO_ROOT / "logs"

def ensure_directories():
    """Ensure all required runtime directories exist."""
    for d in [HARNESS_DIR, AGENTS_DIR, TOOLS_DIR, LOGS_DIR]:
        d.mkdir(parents=True, exist_ok=True)

def get_env_summary() -> dict:
    """Return summary of current environment keys and tool availability."""
    return {
        "anthropic_key_set": bool(os.getenv("ANTHROPIC_API_KEY")),
        "gemini_key_set": bool(os.getenv("GEMINI_API_KEY")),
        "openai_key_set": bool(os.getenv("OPENAI_API_KEY")),
        "amigo_root": str(AMIGO_ROOT),
        "default_target": str(DEFAULT_TARGET_DIR),
    }
