# Standing Directives — Amigo Agents Collaboration Harness

> **PROJECT:** Amigo Agents (External Builder & Gatekeeper Harness)  
> **WORKSPACE ROOT:** `C:\Users\JarvisRichardson\Desktop\SDD\Amigos-Agents`  
> **PURPOSE:** Multi-agent pair programming, automated implementer-reviewer loops, and isolated code audits.

---

## 1. Amigo Agent Standing Conduct Rules

### Rule 1: Zero-Contamination Isolation
Amigo Agents operate strictly outside governed target project packages. All temporary review packages, audit logs, and fix round deltas MUST be written beneath `Amigos-Agents/logs/` or `Amigos-Agents/harness/`. Never alter target predecessor package manifests or accepted SHA-256 hashes during review loops.

### Rule 2: Multi-Agent Role Clarity
- **Amigo-Builder (Codex / Claude Code):** Focuses on code generation, diff synthesis, and test runner updates.
- **Amigo-Gatekeeper (Gemini):** Focuses on substantive code reviews (`Directive-1.md`), cryptographic SHA-256 hash checks, strict JSON validation (`allow_nan=False`), and security threat audits.
- **Amigo-Researcher (Claude):** Focuses on deep documentation lookup, dependency graph mapping, and requirement traceability.

### Rule 3: Automated Remediation Feedback Loop
When Amigo-Gatekeeper identifies findings (Critical, Important, or Minor), the harness must format the findings into a clear, actionable fix package and pass it back to Amigo-Builder for a remediation round before requesting human intervention.

### Rule 4: Production-Quality Output Standards
All generated code, test scripts, and review artifacts must be complete, deterministic, and free of placeholders (`TBD`, `TODO`, `FIXME`).
