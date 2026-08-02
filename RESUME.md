# RESUME — where this repo stands and where to start

**Last session ended:** 2026-08-02 · `main` at `1de4d49`
**Next session target:** Ubuntu dev server (moving off Windows/WSL)

Read this first. It is written for the machine you are moving *to*, not the one you left.

---

## 1. Where we are

`main` is green, protected, and pushed. Nothing is half-finished.

```text
main            1de4d49   == origin/main, tree clean
tests           162 passed  (Python 3.11 and 3.12)
dashboard       tsc --noEmit exit 0 · vite build ok · eslint 0 errors, 9 advisory warnings
CI              .github/workflows/ci.yml — green
branch ruleset  20167729 "main protection" — ACTIVE
```

**What shipped recently**

- **Kimi K3 as a config-switchable Gatekeeper provider.** `GATEKEEPER_PROVIDER=gemini|kimi`,
  Gemini is the default. Live-verified against the real Moonshot API.
- **Merge gate no longer fails open.** An empty Gatekeeper response used to parse to zero findings
  — which reads as "patch is clean" — so an unreviewed patch got approved. Both providers now emit
  a blocking WARNING.
- **Provider-aware health/status.** `/api/system/health` checks only the *active* provider's key.
  It used to report a missing `GEMINI_API_KEY` on a working Kimi config (false alarm) while never
  checking `MOONSHOT_API_KEY` at all (false all-clear — the dangerous half).
- **Audit attribution.** Gatekeeper events and transcript rounds record which provider and model
  actually ran. Missing attribution persists as `null`, never a guess.
- **Portable target dir.** `DEFAULT_TARGET_DIR` resolves from `AMIGO_TARGET_DIR`, falling back to
  the repo root. This is what made the suite run on Linux at all — see §2.
- **CI gate + CodeRabbit App.** Tests, typecheck, build, lint and automated review all run on every
  PR with nobody triggering them.
- **History rewrite.** `logs/`, `research/`, `docs/`, `reviews/` were purged from all history
  (32 files, 254 objects) and force-pushed. 115 commits → 65.

---

## 2. First 20 minutes on the Ubuntu box

### The one thing that will stop you dead

**`.env` is gitignored and will not be on the server.** It lives only on the previous workstation
and is the one file that must be reproduced out of band — never committed, never pasted into a
chat, an issue, or a CI variable that echoes.

`docs/KEYS.MD` is gitignored too, but leave it behind: nothing in the harness reads it. It is a
scratch file, and copying it forward would put a second plaintext copy of the same secrets on a
new host for no gain.

Reproduce `.env` over an encrypted channel — `scp` over SSH, a password manager, or editing the
file directly on the server through VS Code Remote-SSH (which keeps the values out of shell
history on both machines). Then restrict it:

```bash
chmod 600 .env
```

Run that after saving, not before: with a typical `022` umask VS Code creates the file at mode
`0644`, readable by every account on the box.

Do not `cat`, `echo` or otherwise print it. Rotate anything that reaches a log.

`.env` needs, at minimum:

```dotenv
BRIDGE_API_KEY=               # NOT a vendor key -- generate your own, see below
ANTHROPIC_API_KEY=…
OPENAI_API_KEY=…
GEMINI_API_KEY=…
MOONSHOT_API_KEY=…
GATEKEEPER_PROVIDER=kimi      # current setting; unset or "gemini" for the default
```

`BRIDGE_API_KEY` is the one that is easy to miss: it is the bridge's own shared secret, not
something a vendor issues, so there is nothing to transfer — generate a fresh one on the server:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

`harness/bridge.py` raises at startup without it and every route 401s until it matches, so the
bridge will not come up on a freshly-populated `.env` that omits it.

`harness/config.py` reads `.env` at import with `os.environ.setdefault`, so real environment
variables win over the file.

### Setup

```bash
# Bootstrap first. On a minimal 24.04 image none of these are guaranteed present,
# and every step below needs one of them.
sudo apt update
sudo apt install -y git curl unzip python3-venv

git clone https://github.com/hanax-ai/sdd-core-citadel.git
cd sdd-core-citadel

# Python — Ubuntu 24.04 enforces PEP 668, so a venv is mandatory, not optional.
# `pip install` outside one fails with externally-managed-environment.
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q                        # expect: 162 passed

# Dashboard — use Bun, NOT npm.
# dashboard/bun.lock is the tracked lockfile; npm ignores it and resolves fresh
# versions, so npm gives you a different dependency tree than CI tests.
# Piping a remote script to a shell: download and read it first. That is how the
# CodeRabbit installer was vetted in this repo, and it is the control that the
# LiteLLM supply-chain compromise defeated for everyone who skipped it.
curl -fsSL https://bun.sh/install -o /tmp/bun-install.sh
sed -n '1,200p' /tmp/bun-install.sh          # read it; `less` is not guaranteed installed
bash /tmp/bun-install.sh && rm -f /tmp/bun-install.sh   # bash, not sh -- the script uses bashisms
export PATH="$HOME/.bun/bin:$PATH"           # bun is not on PATH in this shell until you do this
cd dashboard && bun install --frozen-lockfile
bun run typecheck && bun run build && bun run lint
```

### Things that get *easier* on Ubuntu

- **CodeRabbit CLI runs natively.** No WSL shim needed. The four shims in
  `~/.local/bin` on Windows (`coderabbit`, `cr`, `.cmd` twins) exist only because there is no
  Windows binary. On Linux, same download-then-read pattern as Bun above:

  ```bash
  curl -fsSL https://cli.coderabbit.ai/install.sh -o /tmp/cr-install.sh
  sed -n '1,200p' /tmp/cr-install.sh
  CI=1 sh /tmp/cr-install.sh && rm -f /tmp/cr-install.sh   # CI=1 skips the interactive login
  export PATH="$HOME/.local/bin:$PATH"                    # installs here; not on PATH until exported

  # Prompt for the key rather than typing it inline -- an inline --api-key value
  # lands in ~/.bash_history. Get an *Agentic* key (user API keys are rejected)
  # from https://app.coderabbit.ai/settings/api-keys
  read -rs -p 'CodeRabbit Agentic API key: ' CR_KEY && echo
  coderabbit auth login --api-key "$CR_KEY"; unset CR_KEY
  ```

  Requires `unzip` and `git`, both in the bootstrap above. Note the CLI does **not** read
  `CODERABBIT_API_KEY` as an environment variable — it must be passed to `--api-key`.
- **No CRLF problem.** `.gitattributes` is `* text=auto eol=lf`. On Windows, agents rewriting
  Python files kept reintroducing CRLF and `core.safecrlf` blocked commits with
  `fatal: CRLF would be replaced by LF`. That failure mode disappears.
- **Windows `curl` could not reach external HTTPS** on the old box (`CRYPT_E_NO_REVOCATION_CHECK`,
  Norton TLS interception). Diagnostics had to run from WSL. Not an issue on Ubuntu.

### Things to rebuild, not copy

- **`.codegraph/`** is gitignored and machine-specific. Rebuild with `codegraph init`.
  Use `codegraph_explore` before grep/Read — it returns verbatim source plus blast radius in one
  call, and it is what caught that `DEFAULT_TARGET_DIR` was the security allowlist root.
- **`.venv/`, `node_modules/`** — rebuild, do not copy. Compiled deps differ.

### Left behind on Windows — decide before wiping that machine

**`<workstation>/SDD/citadel-backup.git`** — exact path kept in local notes, deliberately not
written into this tracked file — is the **only surviving copy of pre-rewrite history** (115 commits, tip `ea6f6e7`, all 254 purged objects). It already recovered 9
files once. Nothing on GitHub has it. If that machine is wiped, it is gone permanently.

---

## 3. Where to start — backlog, highest value first

### A. Three verified engine defects, all silent-wrong-behaviour

These were confirmed by reading source during the Control Plane review. All three are controls that
report success while doing nothing — the same failure shape, three times.

**A1 — `max_rounds` is discarded.** Validated 1–6 at two layers, then never passed to the loop.

```text
dashboard/src/lib/citadel/contract.ts:190   max_rounds: z.number().int().min(1).max(6)
harness/bridge.py:319                       RunTaskRequest.max_rounds (default 3, ge=1, le=6)
harness/bridge.py:468-473                   run_collaboration_cycle(target_dir, task_description,
                                                                    run_id, on_event)  ← not passed
harness/remediation_loop.py:52              signature has no max_rounds parameter
harness/remediation_loop.py:23              MAX_ROUNDS = 3
```

Select 6, get 3. This is a *governance* bug, not just a UI bug: `max_rounds` is the operator's
control over how many times an unreviewed patch regenerates before a human sees it, and it fails
**open** — in the permissive direction. Fix: thread the parameter through `execute_run` into
`run_collaboration_cycle`, default `MAX_ROUNDS`, and add a test asserting a 1-round request
produces exactly one Builder invocation.

**A2 — Cancel does not cancel.** `dashboard/src/hooks/useAgentStream.ts:189`:

```ts
const cancel = useCallback(() => {
  cancelled.current = true;
  teardown();              // closes the EventSource. That is all.
  setConnection("closed");
  setStatus("cancelled");  // reports success to the operator
}, [teardown]);
```

No HTTP call to the bridge. And `harness/bridge.py:385` `_track()` holds a deliberate strong
reference so the asyncio task survives — the comment says so. The run continues to completion,
billing all three vendors, writing SQLite and a transcript. Fix: `POST /api/run-task/{id}/cancel`
that calls `task.cancel()` and emits a terminal event — **or remove the button.** A control that
reports success while doing nothing is worse than no control.

**A3 — `amigo/TaskDispatcher` discards every input.**
`dashboard/src/components/amigo/TaskDispatcher.tsx:58` calls `run.start()` with **no arguments**,
then toasts the `rounds` value it just discarded. There are two `TaskDispatcher` components
(`citadel/` and `amigo/`), both hardcoding the same absolute Windows path as a default, which will not
resolve on Ubuntu at all. Establish which is live, delete the other.

Given all three are the same failure shape, consider one integration test over the dispatch surface
rather than three isolated fixes.

### B. Feature backlog (from `docs/implementation_plan.md`, gitignored — copy it across)

- `tools/sentry_adapter.py` — no error/traceback ingestion path exists at all
- `logs/evidence_store.json` — evidence is in-memory + per-run transcript only
- `tools/test_harness.py` — automated end-to-end test; today it is a manual subagent dispatch
- Round-level attribution is *recorded* but `bridge.py`'s transcript endpoint returns `events`
  only, so the UI cannot consume `gatekeeper_provider` / `gatekeeper_model`
- Dashboard Live-mode click-through (API-level dispatch is proven; the UI path is not)

### C. Housekeeping

- `citadel.sqlite3` is untracked and un-ignored; add it to `.gitignore` or delete it
- `.agents/**` is worth adding to `.coderabbit.yaml` path filters — the vendored `blueprint`
  gitlink burned a CodeRabbit finding slot on two consecutive reviews before it was removed

---

## 4. Open items that need you, not the code

| Item | State |
|---|---|
| GitHub Support ticket **#4621084** | Filed 2026-08-01, awaiting action. Sensitive-data removal: server-side `gc` + cached-view purge after the history rewrite. **Verify rather than trust "completed"** — see below. |
| `citadel-backup.git` | Retain until the ticket is confirmed resolved. Only pre-rewrite copy. |
| Admin bypass on ruleset `20167729` | `RepositoryRole 5` bypasses branch protection. It was load-bearing for the force-push and is no longer needed for planned work. Remove it for a stricter posture, or keep it as a recovery path — a solo maintainer with no bypass has none. |

**How to verify the Support ticket actually completed:**

```bash
gh api repos/hanax-ai/sdd-core-citadel/commits/ea6f6e71a029b3dae80dfe9abe55a517b479da63
gh api repos/hanax-ai/sdd-core-citadel/commits/3da92c4743ddc451033607fe865738532750c5d7
```

Eight orphaned SHAs returned `200` when the ticket was filed despite being unreachable from any
ref. **Success means they stop resolving.** Full list and the ticket text are in
`docs/github-support-request-I17.md` (gitignored — copy it across).

**Not removed, by explicit decision:** the previous workstation's username, and an absolute path to
an unrelated local project, remain in six tracked source files (`AGENTS.md`, `README.md`,
both `TaskDispatcher.tsx`, `fixtures.ts`, `routes/index.tsx`) since the initial commit. Removing
them needs a source change *plus* a second force-push. Recorded in RAID `I17`.

---

## 5. How work lands now

`main` is protected. Ruleset `20167729` requires:

- PR before merging (0 approvals — you cannot approve your own)
- **Conversation resolution** — this is what makes CodeRabbit findings actually block
- Four checks green: `Python 3.11`, `Python 3.12`, `Dashboard typecheck, build, lint`, `CodeRabbit`
- Linear history; force-push and deletion blocked
- Merge methods: squash or rebase — **use `--rebase`** to preserve separate commits

```bash
git checkout -b feat/<thing>
# … work …
gh pr create --base main
# CodeRabbit reviews automatically; CI runs automatically
gh pr merge <n> --rebase --delete-branch
```

Fixes are applied via CodeRabbit's 🪄 **Autofix** checkbox or `@coderabbitai autofix`, deliberately
human-triggered. The reasoning — including why `claude-code-action` auto-fix was evaluated and
rejected — is recorded in `.coderabbit.yaml`.

---

## 6. Gotchas worth knowing before you hit them

- **Provider-invariance is enforced.** `tools/check_provider_invariance.py` compares JUnit XML
  across three `GATEKEEPER_PROVIDER` settings. Three green runs proving each config passes is *not*
  the same as proving they ran the same tests — a provider-dependent skip would otherwise pass
  silently.
- **`vite build` does not typecheck.** esbuild strips types without checking them. `bun run
  typecheck` is a separate step for that reason. A green build is not a green typecheck.
- **`think: false` on the Kimi path survives `drop_params` only because `ollama_chat` is not an
  OpenAI-compatible provider.** Not relevant to this repo directly, but the same class of silent
  passthrough failure applies if provider prefixes change.
- **`.coderabbit.yaml` validates** with `coderabbit config validate` — use it. Unknown keys nested
  under `reviews:` are accepted *silently*, so a setting can look configured and do nothing.
- **Ubuntu 24.04 enables unattended-upgrades by default**, which can restart services. If you run
  the bridge as a long-lived service, an automatic restart drops it.

---

## 7. Related repositories

- **`hanax-ai/sdd-core-control-plane`** (private) — the seven-agent control plane. An adversarial
  review landed 2026-08-02 at
  `Control-Plane/7.0-Governance/Assessment/Claude-Opus-5_2026-08-02_00-12_ControlPlaneAdversarialReview.md`
  — 46 findings, 21 silent-wrong-behaviour. **That repo is currently diverged (ahead 1, behind 1)
  and was deliberately left unpushed.** Reconcile it before doing further work there.
- Three of that review's findings are engine defects and are reproduced as §3A above.
