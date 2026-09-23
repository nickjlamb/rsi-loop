"""Optimiser package: the LLM agent that proposes candidate policies.

Information boundary: this package builds the optimiser's context from the
current policy, notes, lineage and the VISIBLE report only. It never imports
env/, evaluator/, monitor/ or loop/ (tests/test_layout.py); the one evaluator
it needs, run_visible_eval, is injected by the loop as a callable.

Interface: a structured-output protocol rather than native tool calling, so
that the same prompts and parser serve every provider and model tier (the
Perplexity Agent API, through which the models are reached, has no custom
function tools). See protocol.py.
"""
