"""Dependency direction (design E.1): nothing under policy/, sandbox/ or optimizer/
may import from env/, evaluator/, monitor/ or loop/."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN = re.compile(r"^\s*(from|import)\s+(env|evaluator|monitor|loop)\b", re.M)


def test_policy_side_packages_do_not_import_the_evaluator_side():
    for pkg in ("policy", "sandbox", "optimizer"):
        for py in (ROOT / pkg).glob("**/*.py") if (ROOT / pkg).exists() else []:
            assert not FORBIDDEN.search(py.read_text()), f"{py} imports from the evaluator side"


def test_gen0_policy_imports_only_the_standard_library_and_the_contract():
    src = (ROOT / "policy" / "policy_v0.py").read_text()
    imports = re.findall(r"^\s*(?:from\s+(\S+)|import\s+(\S+))", src, re.M)
    mods = {a or b for a, b in imports}
    assert mods <= {"__future__", "math", "typing", "policy.contract"}, mods
