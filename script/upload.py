import os
import sys
import importlib

here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_version() -> str:
    """
    Return version.
    """
    sys.path.insert(0, here)
    return importlib.import_module("a2wsgi").__version__


os.chdir(here)
os.system(f"poetry version {get_version()}")
os.system("git add a2wsgi/* pyproject.toml")
os.system(f'git commit -m "v{get_version()}"')
os.system("git push")
os.system("poetry publish --build")
os.system("git tag v{0}".format(get_version()))
os.system("git push --tags")
