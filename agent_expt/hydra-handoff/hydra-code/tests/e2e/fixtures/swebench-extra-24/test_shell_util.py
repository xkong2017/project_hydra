from shell_util import run_ls


def test_run_ls():
    result = run_ls(".")
    assert result.returncode == 0


def test_run_ls_injection():
    result = run_ls(".; rm -rf /")
    assert result.returncode != 0, "Shell injection should be blocked!"
