import subprocess
import shlex


def run_command(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, shell=True)


def run_ls(path):
    return run_command(["ls", "-la", path])


def run_grep(pattern, filename):
    return run_command(f"grep '{pattern}' {filename}")
