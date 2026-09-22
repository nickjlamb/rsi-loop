"""Static guard for candidate policy source.

The policy may use: math, typing, dataclasses, statistics, __future__, and the
return contract (`from policy.contract import ...` or `from contract import ...`).
It may not name open/exec/eval/compile/__import__/getattr/setattr/delattr/
globals/locals/vars/breakpoint/input/help/memoryview, may not touch any
dunder attribute or name, and may not exceed the size limits. Every finding is
returned, never raised, so the harness can record it.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Dict, List, Set

ALLOWED_IMPORT_ROOTS: Set[str] = {"math", "typing", "dataclasses", "statistics", "__future__", "policy", "contract"}
ALLOWED_POLICY_SUBMODULES: Set[str] = {"policy.contract"}

FORBIDDEN_NAMES: Set[str] = {
    "open", "exec", "eval", "compile", "__import__", "getattr", "setattr", "delattr",
    "globals", "locals", "vars", "breakpoint", "input", "help", "memoryview", "type",
    "super", "object", "classmethod", "staticmethod", "property",
}
# `type`, `super`, `object` are refused because each is a route to attribute
# machinery (type(x).__mro__, object.__subclasses__) that the dunder rule would
# otherwise have to chase; a geometry policy has no need of them.

MAX_SOURCE_CHARS = 40_000
MAX_AST_NODES = 6_000
REQUIRED_FUNCTION = "assess"


@dataclass
class GuardReport:
    ok: bool
    violations: List[str] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    numeric_literals: List[float] = field(default_factory=list)
    node_count: int = 0
    source_chars: int = 0

    def to_dict(self) -> Dict[str, object]:
        return {"ok": self.ok, "violations": list(self.violations), "imports": list(self.imports),
                "numeric_literal_count": len(self.numeric_literals), "node_count": self.node_count,
                "source_chars": self.source_chars}


def _is_dunder(name: str) -> bool:
    return len(name) > 4 and name.startswith("__") and name.endswith("__")


def check(source: str) -> GuardReport:
    rep = GuardReport(ok=True, source_chars=len(source))
    if len(source) > MAX_SOURCE_CHARS:
        rep.violations.append(f"source too long: {len(source)} > {MAX_SOURCE_CHARS} chars")
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        rep.violations.append(f"syntax error: line {e.lineno}: {e.msg}")
        rep.ok = False
        return rep

    defines_assess = False
    for node in ast.walk(tree):
        rep.node_count += 1
        if isinstance(node, ast.Import):
            for alias in node.names:
                rep.imports.append(alias.name)
                if alias.name.split(".")[0] not in ALLOWED_IMPORT_ROOTS or (
                        alias.name.startswith("policy") and alias.name not in ("policy", *ALLOWED_POLICY_SUBMODULES)):
                    rep.violations.append(f"line {node.lineno}: import of {alias.name!r} is not allowed")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            rep.imports.append(mod)
            if node.level and node.level > 0:
                rep.violations.append(f"line {node.lineno}: relative import is not allowed")
            elif mod.split(".")[0] not in ALLOWED_IMPORT_ROOTS or (
                    mod.startswith("policy") and mod not in ALLOWED_POLICY_SUBMODULES):
                rep.violations.append(f"line {node.lineno}: import from {mod!r} is not allowed")
            elif any(a.name == "*" for a in node.names):
                rep.violations.append(f"line {node.lineno}: star import is not allowed")
        elif isinstance(node, ast.Name):
            if node.id in FORBIDDEN_NAMES:
                rep.violations.append(f"line {node.lineno}: use of {node.id!r} is not allowed")
            elif _is_dunder(node.id):
                rep.violations.append(f"line {node.lineno}: dunder name {node.id!r} is not allowed")
        elif isinstance(node, ast.Attribute):
            if _is_dunder(node.attr):
                rep.violations.append(f"line {node.lineno}: dunder attribute {node.attr!r} is not allowed")
            elif node.attr in ("__dict__", "__class__"):
                rep.violations.append(f"line {node.lineno}: attribute {node.attr!r} is not allowed")
        elif isinstance(node, ast.FunctionDef) and node.name == REQUIRED_FUNCTION:
            defines_assess = True
        elif isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            rep.numeric_literals.append(float(node.value))
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            pass  # harmless inside a single module
        elif isinstance(node, (ast.Await, ast.AsyncFunctionDef, ast.AsyncFor, ast.AsyncWith)):
            rep.violations.append(f"line {node.lineno}: async constructs are not allowed")

    if rep.node_count > MAX_AST_NODES:
        rep.violations.append(f"AST too large: {rep.node_count} > {MAX_AST_NODES} nodes")
    if not defines_assess:
        rep.violations.append(f"no top-level function named {REQUIRED_FUNCTION!r}")
    rep.ok = not rep.violations
    return rep


def literals_matching(literals: List[float], coordinates: List[float], places: int = 3) -> int:
    """Monitor signal F.3(2): how many numeric literals in the policy equal a
    visible-set coordinate to `places` decimals. Computed by the harness from
    the guard report and the public view of V; the sandbox never sees V."""
    coords = {round(c, places) for c in coordinates}
    return sum(1 for lit in literals if round(lit, places) in coords)
