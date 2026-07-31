from harness.config import DEFAULT_TARGET_DIR


def test_default_target_dir_is_a_real_existing_directory():
    assert DEFAULT_TARGET_DIR.exists(), f"{DEFAULT_TARGET_DIR} does not exist"
    assert DEFAULT_TARGET_DIR.is_dir()
