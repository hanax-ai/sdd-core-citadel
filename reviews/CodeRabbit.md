1. CodeRabbit
Test the changed --task path.

The verification step tests --status and bare invocation only. Neither exercises the new asyncio.run(run_collaboration_cycle(...)) path.

Add a CLI test that invokes --task and verifies the async collaboration result.

2. CodeRabbit
Make transcript paths unique.

The filename uses only second-level time precision and the task slug. Two concurrent runs with the same task can write to the same path, causing one transcript to overwrite the other. The transcript also omits run_id.

Include run_id or a UUID in the filename and persist it in the JSON transcript.

3. CodeRabbit
Implement the promised token_metric events.

The interface promises token_metric events, but run_collaboration_cycle() emits only stage_change, agent_message, and run_complete. The Researcher, Builder, and Gatekeeper methods also discard the provider usage fields, so the loop cannot emit token metrics.

Return usage metadata from the agent methods or emit it from the provider boundary. Add a test that asserts at least one token_metric event.

Also applies to: 669-729

4. CodeRabbit
Validate findings before applying the verdict.

json.loads() accepts valid JSON with the wrong shape. For example, findings can be null, a string, or a list of malformed objects. has_blocking_findings() then either crashes or treats unknown severities as non-blocking.

Validate every finding before returning it. Reject malformed findings as a blocking warning, and enforce the declared line, severity, and text types.

Also applies to: 209-223, 451-453

5. CodeRabbit
Restrict focused-file evidence to target_dir.

resolve() followed only by is_file() accepts absolute paths, ../ paths, and symlinks outside target_dir. The collector can therefore read secrets outside the requested workspace and send them to providers or write them to logs.

Resolve the root and candidate, then require the candidate to remain below the root before collecting it.

 def _extract_focus_files(task_description: str, target_dir: Path) -> list[Path]:
     """Find file paths named in the task that actually exist under target_dir."""
+    root = target_dir.resolve()
     found = []
     for token in _PATH_TOKEN.findall(task_description):
-        candidate = (target_dir / token.replace("\\", "/")).resolve()
+        candidate = (root / token.replace("\\", "/")).resolve()
+        try:
+            candidate.relative_to(root)
+        except ValueError:
+            continue
         if candidate.is_file() and candidate not in found:
             found.append(candidate)
Apply suggested diff

6. CodeRabbit
Configure explicit timeouts and close provider clients.

Each call creates a provider client without deterministic cleanup. Configure explicit bounded timeouts for all SDKs; Anthropic and OpenAI otherwise allow their 10-minute default, while Google Gen AI inherits its transport timeout. Close clients in finally, using await client.close() for Anthropic/OpenAI and await client.aio.aclose() for Google Gen AI, or reuse lifecycle-managed clients.

