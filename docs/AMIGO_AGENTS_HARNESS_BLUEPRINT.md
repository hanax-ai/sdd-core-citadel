---
title: Amigo Agents Multi-Agent Collaboration & Review Harness Blueprint
project: Amigo Agents
location: C:\Users\JarvisRichardson\Desktop\SDD\Amigos-Agents
created: 2026-07-30
status: Approved Blueprint
---

# 🤝 Amigo Agents: Multi-Agent Collaboration & Review Harness Blueprint

## 1. Executive Summary & Vision

**Amigo Agents** is an external multi-agent collaboration harness. It orchestrates a team of specialized AI agents—**Amigo-Builder** (Codex / Claude Code), **Amigo-Gatekeeper** (Gemini), and **Amigo-Researcher** (Claude)—to collaborate on software engineering tasks outside governing project directories.

By decoupling the review and execution harness from target codebases, Amigo Agents provide automated pair-programming, substantive gatekeeper code reviews, and schema verification without polluting target repository manifests or breaking SHA-256 integrity trees.

---

## 2. Multi-Agent Roster & Roles

```mermaid
flowchart TD
    HumanOperator["Human Operator"] -->|Assigns Goal / Task| AmigoController["Amigo Harness Controller (runner.py)"]
    
    subgraph AmigoTeam ["The Amigo Agents Roster"]
        AmigoBuilder["🔨 Amigo-Builder<br/>(Codex / Claude Code)<br/>Code Author & Refactorer"]
        AmigoGatekeeper["🛡️ Amigo-Gatekeeper<br/>(Gemini)<br/>Gatekeeper Reviewer"]
        AmigoResearcher["🔬 Amigo-Researcher<br/>(Claude)<br/>Deep Spec & Schema Analyst"]
    end

    AmigoController --> AmigoBuilder & AmigoGatekeeper & AmigoResearcher

    AmigoBuilder -->|"1. Submit Patch / Plan"| AmigoGatekeeper
    AmigoGatekeeper -->|"2. Audit Hashes, Schemas & Traceability"| Verdict{"Pass Gate?"}
    
    Verdict -->|"No (Findings Found)"| AmigoBuilder
    Verdict -->|"Yes (Pass 0 Findings)"| TargetProject["Target Workspace (SDD-Core / Workstation)"]
```

### 1. Amigo-Builder (`agents/builder.json`)
- **Primary Model:** Codex / Claude Code
- **Responsibility:** High-velocity code authoring, diff patch synthesis, implementation plan drafting, and unit test runner updates.

### 2. Amigo-Gatekeeper (`agents/reviewer.json`)
- **Primary Model:** Gemini (Sr. AI Engineer & Full Stack Developer)
- **Responsibility:** Substantive gatekeeper code reviews, cryptographic SHA-256 manifest verification, strict Draft 2020-12 schema validation, and security threat auditing.

### 3. Amigo-Researcher (`agents/researcher.json`)
- **Primary Model:** Claude / Subagent
- **Responsibility:** Deep spec analysis, cross-repository dependency tracing, and requirement-to-test mapping.

---

## 3. Automated Remediation Loop Sequence

```mermaid
sequenceDiagram
    autonumber
    actor User as Human Operator
    participant Runner as Amigo Harness Controller (runner.py)
    participant Builder as Amigo-Builder (Codex)
    participant Gatekeeper as Amigo-Gatekeeper (Gemini)
    participant Target as Target Codebase

    User->>Runner: Submit Goal: "Refactor P2-C7 schema validator"
    Runner->>Builder: Dispatch Implementation Task
    Builder->>Runner: Generate Diff Patch & Plan
    Runner->>Gatekeeper: Dispatch Code Review Audit
    Gatekeeper->>Gatekeeper: Verify SHA-256 Hashes, Schemas & Tests
    alt Findings Detected (Critical / Important)
        Gatekeeper-->>Runner: Return Audit Report with Findings
        Runner->>Builder: Dispatch Remediation Fix Round
        Builder-->>Runner: Submit Revised Patch
    else Zero Findings (PASS)
        Gatekeeper-->>Runner: Return PASS Gate Verdict
        Runner->>Target: Apply Verified Patch
        Runner-->>User: Report Goal 100% Accomplished
    end
```

---

## 4. Key Security & Isolation Rules

1. **External Working Directory:** All temporary review packages, audit logs, and fix round deltas must be written inside `Amigos-Agents/logs/` or `Amigos-Agents/harness/`.
2. **Predecessor Immutability:** Amigo Agents never modify predecessor manifests or accepted package files directly during review cycles.
3. **Deterministic Output:** All code review artifacts use standardized naming (`Gemini_[YYYY-MM-DD]_[HH-MM-SS]_[ReviewType].md`) and clear pass/fail criteria.
