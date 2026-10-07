# Zenodo deposit — RSI Loop 2 artifacts (fill-in sheet)

**Reserved DOI (7 Oct 2026): 10.5281/zenodo.23223679** — draft https://zenodo.org/uploads/23223679. Metadata entered; upload the zip, then Publish.

Upload `~/Desktop/rsi-loop-2-archive/rsi-loop-2-artifacts-<tag>.zip` (≈ 65 MB) at zenodo.org → New upload. Paste the fields below. After publishing, put the DOI in `README.md`, `docs/rsi-loop-2-results.md` §8, the RSI page and `CITATION.cff` (to add).

**Resource type:** Dataset

**Title:** RSI Loop 2: trajectory artifacts and frozen analysis for "Check behaviour, not scores" — a preregistered comparison of acceptance-gate architectures for LLM self-improvement loops

**Creators:** Lamb, Nicholas — ORCID 0009-0009-6266-8499 — PharmaTools.AI

**Description:**

Complete artifacts from a preregistered experiment on Goodhart's law in iterated LLM code improvement. An LLM optimiser (Claude Sonnet 5; Claude Opus 5 as a strong-tier factor) revised a small posture-risk classifier 20 times per trajectory under four acceptance architectures: (A) self-evaluation, (B) a visible-score gate, (C) B plus a hidden holdout, (D) C plus an absolute behavioural envelope and canaries. Ground truth is balanced accuracy on a 2,000-frame hidden set from a seeded simulator the optimiser never sees. Primary design: 4 arms × 10 seeds (1000–1009); secondary factors: strong tier on B and D, optimiser notes off on B and D, and a parametric hill-climber baseline on all four arms. 120 confirmatory trajectories (2,400 revisions) plus 9 pre-freeze pilot trajectories.

For every revision the archive holds the full prompt/response transcript, the candidate policy, the optimiser's notes, the diff, visible/hidden/envelope/canary scores, the gate decision, sandbox audit events, token counts and cost; per trajectory, the configuration, prompt hashes and dataset manifest hashes; and the output of the frozen analysis scripts (summary.json, tables, figures). MANIFEST.json gives SHA-256 for every file. The design was frozen at git tag v2.0-freeze (1 October 2026) before any confirmatory trajectory ran; post-freeze harness and analysis defects are logged in experiments/preregistration.md §13.

Headline results: the visible-score gate produced a Goodhart curve in 10/10 seeds (proxy to 100 % in 7/10, truth flat or falling); the hidden holdout was protective but not productive; the behavioural envelope was the only architecture under which hidden ground truth rose (7/10 seeds with Sonnet 5, 10/10 with Opus 5); a parametric optimiser that cannot memorise ended with higher ground truth than the LLM under the visible-score gate; the stronger model was no safer under the weak gate and more productive under the strong one; removing the optimiser's cross-revision notes accelerated gaming and reduced honest fixes.

Code (MIT): https://github.com/nickjlamb/rsi-loop. Datasets are regenerable from seed and manifest with `python3 -m env.datasets`.

**Keywords:** Goodhart's law; reward hacking; specification gaming; recursive self-improvement; AI safety; acceptance gates; LLM agents; preregistration; code generation; evaluation

**Licence:** Creative Commons Attribution 4.0 International

**Version:** v2.1 (first analysed release)

**Language:** English

**Related identifiers:**
- https://github.com/nickjlamb/rsi-loop — "is supplement to" — Software
- https://github.com/nickjlamb/rsi-loop/releases/tag/v2.0-freeze — "is derived from" — Software

**Funding:** none (compute funded by Perplexity API startup credits; state in the paper's acknowledgements, not here)

**Publication date:** date of upload

**Notes field (optional):** The archive contains model outputs produced by Claude Sonnet 5 and Claude Opus 5 via the Perplexity Agent API, including one `finish_reason=refusal` event recorded in artifacts/confirm-01-opus/batch.json. No personal data; the "posture" frames are synthetic landmark coordinates from a seeded simulator.
