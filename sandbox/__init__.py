"""Sandbox package: runs a candidate policy in a separate interpreter.

Two layers, both of which LOG what they refuse (attempted evaluator-adjacent
access is a monitor signal, design E.1):

  ast_guard.py  static check of the candidate source before it is executed
  runner.py     subprocess execution under `python -I`, an audit hook that
                denies imports outside the whitelist and every file/OS/network
                operation, wall-clock and memory limits, and a determinism
                check (two fresh interpreters must agree on every prediction)

Nothing in this package imports from env/, evaluator/, monitor/ or loop/.
The candidate never sees labels: it receives landmarks and returns labels.
"""
