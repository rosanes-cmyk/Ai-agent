"""Start-up help: find the Python that has the exporter's packages.

The setup steps install the packages into Ai-agent/.venv. A new cmd window
starts without it activated, so plain `python` finds none of them. This
module uses only the standard library, so it still loads then.
"""

import os
import subprocess
import sys

PPC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RERUN_FLAG = "PPC_EXPORT_RERUN"


def project_venv():
    """(folder, python) of the .venv next to ppc/ or inside it, or (None, None)."""

    for root in (os.path.dirname(PPC_DIR), PPC_DIR):
        folder = os.path.join(root, ".venv")
        python = os.path.join(folder, "Scripts", "python.exe") if os.name == "nt" else os.path.join(folder, "bin", "python")
        if os.path.isfile(python):
            return folder, python
    return None, None


def running_in(folder):
    return os.path.normcase(os.path.realpath(sys.prefix)) == os.path.normcase(os.path.realpath(folder))


def explain(problem):
    """Plain-English fix for a missing package."""

    folder, _python = project_venv()
    if folder and not running_in(folder) and not os.environ.get(RERUN_FLAG):
        activate = os.path.join(folder, "Scripts", "activate") if os.name == "nt" else "source " + os.path.join(folder, "bin", "activate")
        return (
            f"Python can't find the package '{problem.name}' because this window isn't using the exporter's .venv.\n"
            f"Run this first, then the same command again:\n  {activate}"
        )
    requirements = os.path.join(PPC_DIR, "requirements.txt")
    return (
        f"Python can't find the package '{problem.name}'. Install the exporter's packages once:\n"
        f'  "{sys.executable}" -m pip install -r "{requirements}"'
    )


def rerun_or_explain(problem, script, args):
    """Exit code after a package is missing at start-up.

    Runs the same command again with the .venv Python when this is another
    Python; otherwise prints what to install.
    """

    folder, python = project_venv()
    if folder and not running_in(folder) and not os.environ.get(RERUN_FLAG):
        try:
            child = subprocess.Popen([python, os.path.abspath(script), *args], env={**os.environ, RERUN_FLAG: "1"})
        except OSError:
            pass
        else:
            while True:
                try:
                    return child.wait()
                except KeyboardInterrupt:
                    continue  # Ctrl+C reaches the child too; it stops on its own
    print(explain(problem), flush=True)
    return 2
