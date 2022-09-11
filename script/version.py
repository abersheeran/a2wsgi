import importlib
import os
import subprocess
import sys

here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_version() -> str:
    """
    Return version.
    """
    sys.path.insert(0, here)
    return importlib.import_module("a2wsgi").__version__


os.chdir(here)
subprocess.check_call(f"pdm version {get_version()}", shell=True)
subprocess.check_call("git add a2wsgi/__init__.py pyproject.toml", shell=True)
subprocess.check_call(f'git commit -m "v{get_version()}"', shell=True)
subprocess.check_call("git push", shell=True)
subprocess.check_call("git tag v{0}".format(get_version()), shell=True)
subprocess.check_call("git push --tags", shell=True)
