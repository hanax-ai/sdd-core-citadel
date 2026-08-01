from pathlib import Path

from harness.config import AMIGO_ROOT, DEFAULT_TARGET_DIR, resolve_default_target_dir


def test_default_target_dir_is_a_real_existing_directory():
    # Has to hold on ANY clone, not just the machine that wrote it. This assertion
    # used to be pinned to a hardcoded absolute path on one developer's machine,
    # so it failed everywhere else -- and made a CI gate impossible to add.
    assert DEFAULT_TARGET_DIR.exists(), f"{DEFAULT_TARGET_DIR} does not exist"
    assert DEFAULT_TARGET_DIR.is_dir()


def test_default_target_dir_falls_back_to_the_repo_root(monkeypatch):
    monkeypatch.delenv("AMIGO_TARGET_DIR", raising=False)
    assert resolve_default_target_dir() == AMIGO_ROOT


def test_amigo_target_dir_env_var_overrides_the_default(monkeypatch, tmp_path):
    # harness/bridge.py already honours AMIGO_TARGET_DIR; config.py now applies it
    # at the source so the CLI, the bridge and the allowlist root agree.
    monkeypatch.setenv("AMIGO_TARGET_DIR", str(tmp_path))
    assert resolve_default_target_dir() == tmp_path.resolve()


def test_blank_amigo_target_dir_counts_as_unset(monkeypatch):
    # Matches resolve_gatekeeper_provider's empty/whitespace rule. A bare
    # `AMIGO_TARGET_DIR=` line in .env or a docker-compose passthrough of an
    # undefined variable must not resolve the target dir to the process cwd.
    monkeypatch.setenv("AMIGO_TARGET_DIR", "   ")
    assert resolve_default_target_dir() == AMIGO_ROOT


def test_relative_amigo_target_dir_resolves_to_an_absolute_path(monkeypatch, tmp_path):
    # bridge.py uses this as the allowlist root for _is_within(); a relative path
    # there would make the traversal guard compare against the process cwd.
    # Setting tmp_path here would prove nothing -- it is already absolute -- so
    # the value under test has to be genuinely relative.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AMIGO_TARGET_DIR", "relative-target")
    resolved = resolve_default_target_dir()
    assert resolved.is_absolute()
    assert resolved == (tmp_path / "relative-target").resolve()


def test_default_target_dir_is_absolute_when_unset(monkeypatch):
    monkeypatch.delenv("AMIGO_TARGET_DIR", raising=False)
    assert resolve_default_target_dir().is_absolute()


def test_repo_root_default_is_the_amigo_agents_checkout():
    # Guards against AMIGO_ROOT drifting if config.py moves: parents[1] from
    # harness/config.py must land on the repo root, not harness/.
    assert (AMIGO_ROOT / "harness" / "config.py").is_file()
    assert isinstance(AMIGO_ROOT, Path)
