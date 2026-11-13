"""Load modules from scripts/ by file path so type checkers resolve them."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load_script(name: str) -> ModuleType:
    # scripts/ stays importable because bootstrap.py imports its sibling modules.
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load script: " + name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
