import harness.remediation_loop as remediation_loop
from harness.runner import main


def test_status_flag_prints_env_summary(capsys):
    exit_code = main(["--status"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Amigo Agents Environment Status" in captured.out


def test_task_flag_runs_async_collaboration_cycle_and_prints_result(tmp_path, monkeypatch, capsys):
    captured_args = {}

    async def fake_run_collaboration_cycle(target_dir, task_description):
        captured_args["target_dir"] = target_dir
        captured_args["task_description"] = task_description
        return {
            "verdict": "PASS",
            "log_path": str(tmp_path / "transcript.json"),
            "patch_text": "--- a/file.py\n+++ b/file.py\n",
        }

    monkeypatch.setattr(remediation_loop, "run_collaboration_cycle", fake_run_collaboration_cycle)

    exit_code = main(["--task", "fix the bug", "--target-dir", str(tmp_path)])

    assert exit_code == 0
    assert captured_args["task_description"] == "fix the bug"
    assert str(captured_args["target_dir"]) == str(tmp_path)

    captured = capsys.readouterr()
    assert "PASS" in captured.out
    assert "--- a/file.py" in captured.out
