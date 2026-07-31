# Gemini Review — Claude Code & Gemini CLI MCP Tooling Integration Guide
**Reviewer:** Gemini (Sr. AI Engineer & Full Stack Developer)
**Date:** 2026-07-30
**Time:** 20:27:00 -05:00
**Review Type:** Technical Integration Guide & Architecture Note
**Topic:** Model Context Protocol (MCP) Bridges & Cross-Provider Configuration for Claude Code, Google Gemini, and OpenAI Codex
**Target Directory:** `C:\Users\JarvisRichardson\Desktop\SDD\Amigos-Agents\reviews\`

---

## 🏛️ Executive Summary

Multiple community-built Model Context Protocol (MCP) servers allow **Claude Code** to connect directly to **Google Gemini models**, the **Gemini CLI**, and **OpenAI Codex**. 

By linking these AI ecosystems via MCP, Claude Code can leverage Gemini's 1M+ token context window, multimodal visual analysis, and specialized Google Search grounding features, while simultaneously utilizing OpenAI Codex as an automated secondary auditor and "devil's advocate" reviewer directly within your terminal workspace.

---

## 🌐 Part 1: Linking Claude Code to Google Gemini

### 🔗 One-Line Installation

To instantly bridge Claude Code with Gemini, execute the following command in your terminal:

```bash
claude mcp add gemini-cli -- npx -y gemini-mcp-tool
```

This command automatically downloads, configures, and registers the **`gemini-mcp-tool`** extension into your active Claude Code terminal environment.

### ⚙️ Command Breakdown

```mermaid
flowchart LR
    CMD["claude mcp add"] --> NAME["gemini-cli"]
    NAME --> SEP["--"]
    SEP --> EXEC["npx -y"]
    EXEC --> PKG["gemini-mcp-tool"]
```

| Command Segment | Technical Description & Purpose |
| :--- | :--- |
| **`claude mcp add`** | Tells Claude Code to register and activate a new Model Context Protocol (MCP) tool server. |
| **`gemini-cli`** | The custom local identifier assigned to this specific Gemini tool inside your Claude environment. |
| **`--`** | Command separator; isolates Claude's CLI arguments from the execution command that follows. |
| **`npx -y`** | Node.js package runner that downloads and executes the package dynamically without cluttering global disk space (`-y` auto-approves installation prompts). |
| **`gemini-mcp-tool`** | The open-source bridge package that exposes Gemini API capabilities to Claude Code over MCP stdio. |

### 🔄 Gemini Runtime Workflow

Once registered, Claude Code gains an intelligent background bridge to Google Gemini:

```mermaid
flowchart TD
    User["Developer Terminal (Claude Code)"] -->|"Task: Analyze 1M Token Log / Image File"| Claude["Claude Code Engine"]
    Claude -->|"Invoke MCP Tool: gemini-cli"| MCPBridge["gemini-mcp-tool Bridge (npx)"]
    MCPBridge <-->|"Gemini API / CLI Execution"| Gemini["Google Gemini (1M+ Context & Multimodal)"]
    Gemini -->|"Processed Result & Embeddings"| MCPBridge
    MCPBridge -->|"Structured MCP Response"| Claude
    Claude -->|"Final Synthesized Output"| User
```

1. **Massive Context Offloading:** When analyzing massive codebases or 100k+ line log files exceeding standard bounds, Claude Code delegates heavy retrieval context to Gemini's 1M+ token window.
2. **Multimodal Analysis:** Image diagrams, architecture mockups, and UI screenshots can be processed by Gemini and returned to Claude Code in real time.
3. **Seamless Terminal Workflow:** The bridge operates silently in the background, allowing you to remain inside your primary Claude Code console while using Gemini's compute capabilities.

---

## ⚡ Part 2: Linking Claude Code to OpenAI Codex

When you install the official **[OpenAI Codex Plugin for Claude Code (`openai/codex-plugin-cc`)](https://github.com/openai/codex-plugin-cc)**, it maps the capabilities of the OpenAI Codex engine directly into your Claude terminal. This lets you run multi-agent workflows, shifting heavy or highly critical evaluation jobs to a fine-tuned reasoning model like `codex-1` without dropping out of your Claude workflow.

### 🔗 One-Line Installation

To link Codex into your Claude Code terminal environment:

```bash
claude mcp add codex -- codex-mcp-server
```

### ⚙️ Command Breakdown

| Command Segment | Technical Description & Purpose |
| :--- | :--- |
| **`claude mcp add`** | Tells Claude Code to fetch and configure a new external MCP tool. |
| **`codex`** | Sets the internal identifier Claude uses to reference this connection. |
| **`--`** | Separates core Claude commands from actual executable arguments. |
| **`codex-mcp-server`** | Invokes OpenAI's background utility, bridging Claude to your local authenticated Codex environment. |

### 🔀 Shared MCP Server Configuration (Claude Code vs Codex CLI)

Claude Code and OpenAI Codex CLI do not automatically sync their configurations. Claude reads its integrations from a local JSON file (`~/.claude/settings.json`), while Codex looks at a global or project-level TOML file (`~/.codex/config.toml` or `~/.config/codex/config.toml`).

If you want both coding agents to have access to the exact same background tool (like an app router, database, or browser automation), you must wire them into both paths:

#### 1. Claude Code Config (`~/.claude/settings.json`)
Claude connects via standard `stdio` transport using standard JSON:

```json
{
  "mcpServers": {
    "composio-router": {
      "command": "npx",
      "args": [
        "-y",
        "@composio/mcp-gateway"
      ],
      "env": {
        "COMPOSIO_API_KEY": "your_key_here"
      }
    }
  }
}
```

#### 2. Codex Config (`~/.codex/config.toml` or `~/.config/codex/config.toml`)
To provision the exact same tool for the Codex CLI or its VS Code extension, map those same execution fields into `[mcp_servers]` TOML blocks:

```toml
[mcp_servers.composio-router]
command = "npx"
args = ["-y", "@composio/mcp-gateway"]
enabled = true

[mcp_servers.composio-router.env]
COMPOSIO_API_KEY = "your_key_here"
```

*(Alternatively, you can register a remote cloud-based service into Codex using the CLI: `codex mcp add composio-router --url https://example.com`)*.

---

## 🤖 Part 3: Codex Commands & Review Workflows in Claude Code

The official Codex Plugin grants you access to **7 key slash commands** and modifiers inside your Claude terminal:

| Slash Command / Modifier | Operational Function & Purpose |
| :--- | :--- |
| **`/codex review`** | Instructs Codex to perform a polite, read-only audit of your active git changes or specified files. Flags potential syntax or logical errors without modifying source files. |
| **`/codex adversarial-review`** | Enlists Codex as a strict "devil's advocate" against a plan or architectural approach Claude Code just generated. Deliberately tries to spot edge cases, security vulnerabilities, or infrastructure assumptions Claude missed. |
| **`/codex rescue`** | Triggers an extensive, codebase-wide audit rather than target-scanning single modules. Evaluates macro file dependencies, maps out larger architecture drift, and allows plain-English problem prompts. |
| **`/codex setup`** | Initializes, checks, or re-authenticates your local Codex session, pairing credentials from your ChatGPT subscription or OpenAI API key directly inside the plugin context. |
| **`-- background`** *(Dash Modifier)* | Appended to heavy sweeps (e.g., `/codex rescue -- background`). Forces the process to handle long-token tasks asynchronously in the cloud sandbox so your main Claude Code CLI terminal doesn't lock up. |
| **`/codex status`** | Checks the real-time compilation or audit status of a background job you previously spun up. |
| **`/codex results`** | Fetches the completed analysis from your finished background job and pipes OpenAI's evaluation directly into your active Claude session context. |
| **`/codex cancel`** | Immediately kills a running background execution or pending evaluation queue to prevent unnecessary token consumption. |

---

## 🛠️ Part 4: Global MCP Server Setup in Codex CLI

If you are working in reverse and adding Model Context Protocol tools directly into the **Codex CLI** instead of Claude Code, Codex handles global tool configuration via its **TOML file**:

```bash
codex mcp add <server-name> --url <mcp-server-url>
```

---

## 📚 References & Resources

- [Official OpenAI Codex Plugin Repository (`openai/codex-plugin-cc`)](https://github.com/openai/codex-plugin-cc)
- [OpenAI Codex Plugin Announcement](https://community.openai.com/t/introducing-codex-plugin-for-claude-code/1378186)
- [Syncing Codex & Claude Configs](https://community.openai.com/t/sync-codex-and-claude-code-configs-skills-agents-mcp-permissions/1380517)
- [Gemini MCP Server Reddit Overview](https://www.reddit.com/r/ClaudeCode/comments/1lxqlki/gemini_mcp_server_utilise_googles_1m_token/)
- [Gemini MCP Tool GitHub Repository](https://github.com/jamubc/gemini-mcp-tool)
- [Claude Code & Codex Setup Guide](https://www.mostlyserious.io/insights/claude-code-codex-guide-nontechnical)
- [Claude Code & Codex MCP Reddit Discussion](https://www.reddit.com/r/ClaudeCode/comments/1qwd8zs/is_anybody_else_using_claude_code_with_codex_mcp/)
- [Codex CLI config.toml Deep Dive](https://ofox.ai/blog/codex-cli-config-toml-deep-dive/)
- [Setting up MCP in Codex CLI TOML Guide](https://www.reddit.com/r/ChatGPTCoding/comments/1n3y2vq/setting_up_mcp_in_codex_is_easy_dont_let_the_toml/)

---
*Guide compiled by Gemini. Execution halted as requested.*
