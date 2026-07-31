# Amigo Agents — Code Review Report

**Repository:** `C:\Users\JarvisRichardson\Desktop\SDD\Amigos-Agents`
**Date:** 2026-07-30
**Review type:** Independent follow-up review (fresh pass, not an update of the prior report)
**Prior report referenced:** `reviews/AMIGO_AGENTS_PROJECT_REVIEW_REPORT.md`

---

## 1. Executive Summary

This review covers the Amigo Agents harness repository as it stands today, including the working-tree reorganization that is currently uncommitted. Twenty-one findings were verified, spanning two **critical** platform-breaking bugs, seven **high**-severity documentation/logic defects, six **medium**-severity issues, four **low**-severity items, and two **informational** notes (one positive).

The headline problem is unchanged from before: **the primary CLI entry point still cannot run on a default native-Windows console** (`harness/runner.py`, `harness/remediation_loop.py`) because of unguarded emoji `print()` calls, and the harness's only path defaults still point at a WSL-style location that doesn't exist on this machine. Layered on top of that, the just-performed documentation reorg (files moved into `docs/`) has not been fully propagated — the README's layout tree and the prior review report's own relative links are now stale/broken. Separately, `remediation_loop.py` and `agents/gatekeeper.py` reveal that the "builder → gatekeeper" review loop described in the harness's own docstrings and roadmap does not exist yet in the call graph: no gatekeeper is ever invoked, and the "remediation loop" is a git-status printer.

None of the findings are security vulnerabilities in the traditional sense (subprocess usage is list-form and injection-safe; secrets are correctly gitignored), but several are correctness/usability blockers that make the tool non-functional out of the box on the developer's own platform.

| Severity | Count |
| :--- | :---: |
| Critical | 2 |
| High | 7 |
| Medium | 6 |
| Low | 4 |
| Info | 2 |
| **Total** | **21** |

---

## 2. Changes Since Prior Review

Per `git status`, the working tree currently has an **uncommitted structural reorganization**:

| Change | Detail |
| :--- | :--- |
| Deleted from repo root | `AMIGO_AGENTS_HARNESS_BLUEPRINT.md`, `implementation_plan.md` |
| New untracked directory | `docs/` — now holds `AMIGO_AGENTS_HARNESS_BLUEPRINT.md` and `implementation_plan.md` |
| New untracked directory | `reviews/` — now holds the prior review report (`AMIGO_AGENTS_PROJECT_REVIEW_REPORT.md`) |
| Commit status | Not committed — `git status` shows both deletions and both new directories as pending changes on `main` |

This reorg is directly responsible for two of the high-severity findings below: the prior review report's relative links to the blueprint and implementation plan (`../AMIGO_AGENTS_HARNESS_BLUEPRINT.md`, `../implementation_plan.md`) were written when those files lived at the repo root and are now broken from the report's new location under `reviews/`. Separately, `README.md`'s "Repository Layout" section was already drifting from the real tree before this move (missing `implementation_plan.md` entirely, listing agent/tool files that don't exist) and has not been touched to reflect either the pre-existing drift or the new `docs/`/`reviews/` layout.

Because the move is uncommitted, no git history damage has occurred yet — this is the right moment to fix the resulting broken links and update the README before committing the reorg.

---

## 3. Findings

### 3.1 Documentation & Repository Layout Accuracy

| # | File:Line | Severity | Finding |
| :-: | :--- | :---: | :--- |
| 1 | `README.md:40` | 🔴 High | "Repository Layout" tree is stale against the actual tree on multiple fronts: shows `AMIGO_AGENTS_HARNESS_BLUEPRINT.md` at repo root (it now lives only at `docs/AMIGO_AGENTS_HARNESS_BLUEPRINT.md`); lists `agents/reviewer.json` and `agents/researcher.json` (lines 51–52), neither of which exists (`agents/` actually contains only `builder.json` and `gatekeeper.py`); lists `tools/sha256_verifier.py` and `tools/lint_runner.py` (lines 55–56), neither of which exists (`tools/` actually contains `git_adapter.py`, `linter_adapter.py`, `test_adapters.py`); and omits every real file under `harness/` except `runner.py` (`config.py`, `evidence_collector.py`, `remediation_loop.py` are missing), plus omits `docs/`, `reviews/`, `research/`, `requirements.txt`, `.env.example`, and `.gitignore` entirely. |
| 2 | `reviews/AMIGO_AGENTS_PROJECT_REVIEW_REPORT.md:21` | 🔴 High | Relative link `[AMIGO_AGENTS_HARNESS_BLUEPRINT.md](../AMIGO_AGENTS_HARNESS_BLUEPRINT.md)` is broken — the file was moved to `docs/AMIGO_AGENTS_HARNESS_BLUEPRINT.md` and deleted from the repo root. Correct path from `reviews/` is `../docs/AMIGO_AGENTS_HARNESS_BLUEPRINT.md`. |
| 3 | `reviews/AMIGO_AGENTS_PROJECT_REVIEW_REPORT.md:33` | 🔴 High | Relative link `[implementation_plan.md](../implementation_plan.md)` is broken — the file was moved to `docs/implementation_plan.md` and deleted from the repo root. Correct path from `reviews/` is `../docs/implementation_plan.md`. |
| 4 | `AGENTS.md:16` | 🟡 Medium | Rule 2 instructs Amigo-Gatekeeper to review code "against security guidelines (Directive-1.md)", but no `Directive-1.md` exists anywhere in the repository. The same dangling reference also appears in `README.md:68` and `docs/implementation_plan.md:88`. |
| 5 | `README.md:41` | 🟢 Low | Even independent of the `docs/` move, the Repository Layout section never listed `implementation_plan.md` at all — the tree was already incomplete relative to the project's real top-level files. |
| 6 | `README.md` (repo root) | 🟢 Low | No `LICENSE` file exists at the repo root; `README.md` and `AGENTS.md` contain no licensing section, leaving reuse/redistribution terms undefined. |

### 3.2 Windows Runtime Compatibility

| # | File:Line | Severity | Finding |
| :-: | :--- | :---: | :--- |
| 7 | `harness/runner.py:48,57,61,62,68` | 🔥 Critical | `print()` calls emit emoji glyphs (🤝, 🚀, 📂, ✨) with no encoding guard. Running `python harness\runner.py --status` (or any invocation) on a default-codepage Windows console (cp1252/cp437, no `chcp 65001`, no `PYTHONUTF8=1`) raises `UnicodeEncodeError: 'charmap' codec can't encode character '\U0001f91d'` and the process terminates with a traceback instead of printing status. This is the primary CLI entry point, so the tool is unusable out of the box on native Windows. |
| 8 | `harness/remediation_loop.py:15-16` | 🔥 Critical | Same unguarded-emoji `print()` pattern (📊, ℹ️). Since `run_collaboration_cycle()` is invoked from `runner.py`'s `--task` path (`runner.py:66`), this raises the same `UnicodeEncodeError` the first time a task is dispatched, not just on `--status`. |
| 9 | `harness/config.py:25` | 🔴 High | `DEFAULT_TARGET_DIR` is hardcoded to a WSL-style path (`/mnt/c/Users/JarvisRichardson/Desktop/WiP/SDD-Core-Framework-Analysis`), meaningless on native Windows. On this platform a leading-slash `PurePath` is drive-relative, so `Path(...).resolve()` yields `C:\mnt\c\Users\JarvisRichardson\Desktop\WiP\SDD-Core-Framework-Analysis` — a directory that doesn't exist (empirically confirmed). Running `python harness\runner.py --task "..."` with no `--target-dir` flag causes `get_git_status()` to hit `FileNotFoundError`, caught by `git_adapter.py`'s broad `except`, silently returning `{'is_git': False, 'error': '...'}`. The harness reports "not a git repo" for a target it never actually pointed at. |
| 10 | `tools/test_adapters.py:17` | 🔴 High | The "test" script hardcodes the same WSL-only path as `config.py`, so on native Windows it always exercises `get_git_status()` against a nonexistent directory and reports a false negative — `python tools\test_adapters.py` always prints `Git Status: {'is_git': False, ...}` regardless of whether `get_git_status()` actually works, giving no real signal in either direction. |
| 11 | `tools/test_adapters.py:21-23` | 🔴 High | `sample_json` uses the same drive-relative WSL path, so `mkdir(parents=True)` + `write_text()` creates a spurious directory tree at `C:\mnt\...` instead of touching the real `agents/builder.json` — filesystem pollution from a script whose purpose implies read-only testing. The JSON-validation assertion that follows (line 25) then validates a file the script itself just fabricated at the wrong location, not the project's real config. |

### 3.3 Architecture & Logic Integrity

| # | File:Line | Severity | Finding |
| :-: | :--- | :---: | :--- |
| 12 | `harness/remediation_loop.py:11-21` | 🔴 High | `run_collaboration_cycle()` implements neither a "remediation loop" (per filename) nor a "collaboration cycle" (per its own docstring/name). The function only calls `collect_task_evidence()`, prints the branch/modified-file count and a static string, then returns a dict. No builder or gatekeeper agent is ever invoked, and there is no loop of any kind — contradicting `runner.py`'s module docstring ("Orchestrates multi-agent builder & gatekeeper review loops"). A user running `runner.py --task "fix the failing test"` gets a git-status dump, not a review/remediation cycle. |
| 13 | `agents/gatekeeper.py:10` | 🟡 Medium | `AmigoGatekeeper` is never imported or instantiated anywhere in `harness/` or `tools/` — a repo-wide grep shows matches only inside `gatekeeper.py` itself and in prose docs. The class is fully dead code; the "gatekeeper review" capability `runner.py` advertises does not run. This corroborates finding #12. |

### 3.4 Evidence & Validation Quality

| # | File:Line | Severity | Finding |
| :-: | :--- | :---: | :--- |
| 14 | `harness/evidence_collector.py:35` | 🟡 Medium | `git_diff_summary` silently truncates any diff over 2000 characters with no truncation marker, contradicting the module's own "zero-hallucination evidence-driven" docstring claim (line 4). A 6000-character diff is cut off mid-line/mid-hunk with nothing in the returned dict signaling that truncation occurred. |
| 15 | `harness/evidence_collector.py:23` | 🟡 Medium | `syntax_valid` is hardcoded `True`/`"OK"` for every non-JSON focus file regardless of actual contents (`validate_json_syntax(f) if f.suffix == ".json" else (True, "OK")`). A `.py` file with a real syntax error still produces `{'syntax_valid': True, 'syntax_error': 'OK'}` since no validation is attempted for non-`.json` suffixes — a gatekeeper or reviewer trusting this field would treat broken source as verified-valid. |
| 16 | `agents/gatekeeper.py:20` | 🟢 Low | `format_review_prompt()` truncates `diff_text` to 3000 characters with no truncation indicator — same undisclosed-truncation pattern as #14. Currently low impact only because the class is dead code (#13); becomes relevant the moment it's wired in. |
| 17 | `harness/evidence_collector.py:8` | 🟢 Low | `import json` is unused — `json` is never referenced elsewhere in the file. `collect_task_evidence()` builds/returns a plain dict without serializing or parsing JSON. |

### 3.5 Testing, CI & Dependency Hygiene

| # | File:Line | Severity | Finding |
| :-: | :--- | :---: | :--- |
| 18 | `tools/test_adapters.py` | 🟡 Medium | No automated test framework or CI is configured. `requirements.txt` has no pytest/unittest package; no `pytest.ini`/`pyproject.toml`/`setup.cfg`; no `.github/workflows`. The sole `test_*.py` file just prints results under `if __name__ == "__main__"` — no `assert`, no fixtures, so it neither fails a build nor runs automatically anywhere. Regressions like the Windows Unicode crash (#7/#8) or the destructive write (#11) have no automated gate to catch them. |
| 19 | `requirements.txt` (lines 1–3) | 🟡 Medium | All three pinned dependencies (`rich>=13.7.0`, `jsonschema>=4.20.0`, `pyyaml>=6.0.1`) are declared but never imported anywhere in the codebase. A repo-wide grep for `import rich`/`import jsonschema`/`import yaml` (and `from` variants) across `harness/`, `tools/`, `agents/` returns zero matches — the JSON "schema" validation in `linter_adapter.py` is hand-rolled with stdlib `json`, not `jsonschema`. Unused deps add install/supply-chain surface with no corresponding functionality. |

### 3.6 Security & Secrets Handling

| # | File:Line | Severity | Finding |
| :-: | :--- | :---: | :--- |
| 20 | `.env` | ⚪ Info | Holds live, non-placeholder ANTHROPIC/GEMINI/OPENAI API keys in plaintext. Correctly excluded from git — `.gitignore:12` lists `.env`, `git ls-files` shows only `.env.example` tracked, and `git log --all -p` grepped for the key variable names matches only placeholder values in `.env.example`. No git-history leak. Worth a reminder to rotate keys if this workspace is ever shared, zipped, or backed up as-is. |
| 21 | `tools/git_adapter.py:15` | ⚪ Info (positive) | Subprocess invocation uses list-form args (`subprocess.run(["git"] + args, ...)`, no `shell=True`), so there is no shell-injection vector even though `target_dir`/git args ultimately derive from the CLI `--target-dir` argument. A repo-wide grep for `eval(`, `exec(`, `os.system`, and `shell=True` found zero matches anywhere in the codebase. |

---

## 4. Recommendations (Prioritized)

**Immediate — blocks basic usage on the developer's own platform**

1. Fix the Windows console crash: guard the emoji `print()` calls in `harness/runner.py` (lines 48, 57, 61, 62, 68) and `harness/remediation_loop.py` (lines 15–16) — either reconfigure stdout to UTF-8 (`sys.stdout.reconfigure(encoding="utf-8")`) at entry, or drop the emoji from the strings. This is the single highest-leverage fix; nothing else in the harness matters if the CLI can't start.
2. Correct `DEFAULT_TARGET_DIR` in `harness/config.py:25` to a real, existing Windows path (or remove the hardcoded default entirely and require `--target-dir`, failing loudly if the resolved path doesn't exist rather than letting `git_adapter.py`'s broad `except` mask it as "not a git repo").
3. Fix `tools/test_adapters.py`: replace the hardcoded WSL path (line 17) with a real target, and remove/redirect the `mkdir(parents=True)` + `write_text()` block (lines 21–23) so the script stops writing to a fabricated `C:\mnt\...` tree and instead reads the repo's actual `agents/builder.json` without mutating anything.

**Near-term — fixes stale/broken documentation from the in-progress reorg**

4. Update `README.md`'s "Repository Layout" tree (lines 40–56) to match the real filesystem: remove `agents/reviewer.json`, `agents/researcher.json`, `tools/sha256_verifier.py`, `tools/lint_runner.py`; add `config.py`, `evidence_collector.py`, `remediation_loop.py` under `harness/`; add `docs/`, `reviews/`, `research/`, `requirements.txt`, `.env.example`, `.gitignore`, and `implementation_plan.md`.
5. Fix the two broken relative links in `reviews/AMIGO_AGENTS_PROJECT_REVIEW_REPORT.md` (lines 21 and 33) to point at `../docs/AMIGO_AGENTS_HARNESS_BLUEPRINT.md` and `../docs/implementation_plan.md` respectively, before committing the `docs/`/`reviews/` reorg.
6. Resolve the dangling `Directive-1.md` reference: either add the file or rewrite the rule text in `AGENTS.md:16`, `README.md:68`, and `docs/implementation_plan.md:88` to stop pointing at a nonexistent file.

**Medium-term — closes the gap between what the harness claims to do and what it does**

7. Either rename `remediation_loop.py` to reflect its actual behavior (a git-status collector) or implement the builder→gatekeeper loop its name and `runner.py`'s docstring promise — wire `agents/gatekeeper.py`'s `AmigoGatekeeper` into it so gatekeeper review actually executes instead of being dead code.
8. Add truncation markers to `harness/evidence_collector.py:35` (`git_diff_summary`) and `agents/gatekeeper.py:20` (`format_review_prompt`), so any consumer can tell when evidence was cut off rather than silently trusting an incomplete diff.
9. Fix the misleading `syntax_valid` default in `harness/evidence_collector.py:23` — implement real syntax checking for `.py` files (e.g., `ast.parse`) or rename the field so it doesn't imply validation happened when it didn't.
10. Add a real pytest-based test suite with assertions (not just `main()` prints) plus a CI workflow, so regressions like the Windows crash and the destructive write have an automated gate.

**Housekeeping — low urgency, low effort**

11. Remove the unused `rich`, `jsonschema`, `pyyaml` entries from `requirements.txt`, or start using them if they're planned for near-term work.
12. Remove the unused `import json` in `harness/evidence_collector.py:8`.
13. Add a `LICENSE` file to define reuse/redistribution terms for the repo.
14. As a reminder rather than a code fix: rotate the API keys in `.env` if this workspace is ever shared, zipped, or backed up in a form that could expose the plaintext file.
