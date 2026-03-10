import pytest
import sys
from src.core.platform import (
    is_windows, is_linux, is_mac, get_platform_name,
    normalize_path, to_posix_path, get_shell_command,
    get_home_dir, get_config_dir, get_data_dir,
    get_null_device, get_shell_executable, ensure_dir,
)


def test_platform_detection():
    # At least one should be True
    assert is_windows() or is_linux() or is_mac()


def test_platform_name():
    name = get_platform_name()
    assert name in ("windows", "linux", "macos")


def test_normalize_path():
    result = normalize_path("a/b/c")
    assert isinstance(result, str)
    assert "a" in result and "b" in result and "c" in result


def test_to_posix_path():
    result = to_posix_path("a\\b\\c")
    assert "/" in result
    assert "\\" not in result


def test_shell_command():
    cmd = get_shell_command("echo hello")
    assert isinstance(cmd, list)
    assert len(cmd) >= 2
    if is_windows():
        assert cmd[0] == "cmd"
    else:
        assert cmd[0] == "bash"


def test_shell_executable():
    exe = get_shell_executable()
    assert exe is not None


def test_home_dir():
    home = get_home_dir()
    assert len(home) > 0


def test_config_dir():
    config = get_config_dir()
    assert "mustafacli" in config


def test_data_dir():
    data = get_data_dir()
    assert "mustafacli" in data


def test_null_device():
    null = get_null_device()
    if is_windows():
        assert null == "NUL"
    else:
        assert null == "/dev/null"


def test_ensure_dir(tmp_path):
    test_dir = str(tmp_path / "test_dir" / "sub")
    result = ensure_dir(test_dir)
    assert result == test_dir
    import os
    assert os.path.isdir(test_dir)
