"""A new window without .venv activated still runs the exporter."""

import os
import shutil
import stat
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _plain_python_lacks_yaml():
    return subprocess.run([sys.executable, "-S", "-c", "import yaml"], capture_output=True).returncode != 0


pytestmark = [
    pytest.mark.skipif(os.name == "nt", reason="the fake .venv Python is a shell script"),
    pytest.mark.skipif(not _plain_python_lacks_yaml(), reason="PyYAML loads even without site-packages here"),
]


def copy_of_ppc(tmp_path):
    ppc = tmp_path / "Ai-agent" / "ppc"
    ppc.mkdir(parents=True)
    for name in ("export.py", "requirements.txt"):
        shutil.copy(os.path.join(HERE, name), ppc)
    shutil.copytree(os.path.join(HERE, "ppc_exporter"), ppc / "ppc_exporter", ignore=shutil.ignore_patterns("__pycache__"))
    return ppc


def fake_venv(tmp_path, *python_flags):
    bin_dir = tmp_path / "Ai-agent" / ".venv" / "bin"
    bin_dir.mkdir(parents=True)
    python = bin_dir / "python"
    python.write_text(f'#!/bin/sh\nexec "{sys.executable}" {" ".join(python_flags)} "$@"\n')
    python.chmod(python.stat().st_mode | stat.S_IEXEC)


def run_plain_python(ppc, tmp_path, *python_flags):
    """export.py status; with -S the Python has none of the packages, like a new cmd window."""

    env = {k: v for k, v in os.environ.items() if not k.startswith("GOOGLE_ADS_") and k != "PPC_EXPORT_RERUN"}
    return subprocess.run([sys.executable, *python_flags, str(ppc / "export.py"), "status", "--config", str(tmp_path / "none.yaml")],
                          capture_output=True, text=True, env=env, timeout=120)


def test_runs_again_with_the_venv_python(tmp_path):
    ppc = copy_of_ppc(tmp_path)
    fake_venv(tmp_path)
    result = run_plain_python(ppc, tmp_path, "-S")
    direct = run_plain_python(ppc, tmp_path)
    assert "customer_id: missing" in result.stdout and "Traceback" not in result.stderr
    assert (result.returncode, result.stdout) == (direct.returncode, direct.stdout)


def test_without_a_venv_it_says_what_to_install(tmp_path):
    ppc = copy_of_ppc(tmp_path)
    result = run_plain_python(ppc, tmp_path, "-S")
    assert result.returncode == 2
    assert "Python can't find the package 'yaml'" in result.stdout
    assert "-m pip install -r" in result.stdout and "requirements.txt" in result.stdout
    assert "Traceback" not in result.stderr


def test_a_venv_missing_the_packages_too_stops_after_one_try(tmp_path):
    ppc = copy_of_ppc(tmp_path)
    fake_venv(tmp_path, "-S")
    result = run_plain_python(ppc, tmp_path, "-S")
    assert result.returncode == 2
    assert result.stdout.count("Python can't find the package 'yaml'") == 1
    assert "-m pip install -r" in result.stdout


def test_a_package_missing_later_gets_the_same_help(monkeypatch, capsys):
    sys.path.insert(0, HERE)
    import export

    def needs_google_ads(*_args):
        raise ModuleNotFoundError("No module named 'google'", name="google")

    monkeypatch.setitem(export.COMMANDS, "status", needs_google_ads)
    monkeypatch.setattr(export.startup, "project_venv", lambda: (None, None))
    assert export.main(["status", "--config", os.devnull]) == export.EXIT_SETUP
    assert "Python can't find the package 'google'" in capsys.readouterr().out
