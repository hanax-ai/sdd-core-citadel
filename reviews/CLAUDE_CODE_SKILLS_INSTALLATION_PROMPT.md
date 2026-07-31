# 🤝 Refined Skill Directive: Safe Blueprint Skill Integration

Hello Claude Code. You are acting as **Amigo-Researcher** and **Amigo-Builder** within the **Amigo Agents Multi-Agent Collaboration Harness** located at `C:\Users\JarvisRichardson\Desktop\SDD\Amigos-Agents`.

Following a security audit of third-party repositories, we have eliminated third-party binary scripts and redundant packages. Your task is to safely inspect and integrate the pure markdown **Blueprint** skill.

---

## 🛡️ Security Audit Verdicts & Exclusions

* ❌ **Excluded (`raphaelchristi/harness-evolver`):** UNSAFE. Un-reviewed autonomous execution agent with auto-merging and API key disk persistence.
* ❌ **Excluded (`obra/superpowers`):** REDUNDANT. Superpowers skill suite is already active in the current session.
* ⚠️ **Excluded Executable Binaries (`agnix`, `debug-skill`, `agenttrace`):** EXCLUDED. These are compiled Rust/Go binaries with curl-to-bash / postinstall triggers. We enforce zero unverified binary execution.

---

## 🛠️ Step 1: Safely Clone Pure Markdown `blueprint` Skill

Execute a manual git clone of the pure markdown `blueprint` repository (no piped bash scripts):

```bash
# Create local customization root directory if needed
mkdir -p .agents/skills/

# Safely clone pure markdown blueprint skill
git clone https://github.com/imbue-ai/blueprint.git .agents/skills/blueprint
```

---

## 📋 Step 2: Role-Based Workflow Integration

### 🔬 Amigo-Researcher (Claude) — Spec & Dependency Analyst
* **Skill:** `blueprint` (`.agents/skills/blueprint`)
* **Usage:** 
  - Before writing implementation code, invoke `blueprint` to inspect target repository requirements (e.g. `C:\Users\JarvisRichardson\Desktop\WiP\SDD-Core-Framework-Analysis`).
  - Draft structured implementation plans (`implementation_plan.md`) outlining file dependencies, API contracts, and schema URNs.

---

## ✅ Step 3: Verification & Readiness Check

1. Confirm `.agents/skills/blueprint/SKILL.md` contains pure markdown instructions with no executable binary triggers.
2. Run `python harness/runner.py --status` to confirm harness health.
