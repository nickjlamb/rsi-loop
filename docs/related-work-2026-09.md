# Related work and novelty check — 30 September 2026

Search run before the preregistration, so that the claims are sized against what exists. Web search plus abstracts; full reads still to do for the four starred items before writing.

## Closest work (2025–2026)

| Work | What it does | Overlap with RSI Loop 2 | What it does not do |
| --- | --- | --- | --- |
| ★ **SpecBench** (Zhao, Srikanth, Wu, Jiang; Weco AI; arXiv 2605.21384, May 2026) | 30 systems-programming tasks; agents optimise against visible validation tests, are scored on hidden compositional tests; reward hacking = the visible − hidden gap; a 2,900-line "compiler" that memorised test inputs | Same core quantity (visible − hidden gap); same memorisation route | One-shot tasks, not an iterated loop with an acceptance gate; no comparison of verification architectures; no exact ground truth (hidden tests are still tests) |
| ★ **BAITBENCH** (Prasad et al.; arXiv 2608.30724, Aug 2026) | Planted shortcuts (entity leakage, near-duplicates, no-signal tasks) in ML tasks; 7 frontier agents; 57 % of runs hack; validity-aware prompting cuts it by only 6 points; agents recognise the shortcut and take it anyway | Our B/3 "exact-match safety net" and B/2 "bounded boxes" are the same phenomenon, narrated the same way | Measures rates per run, not dynamics over generations; mitigations are prompts, not gate architectures |
| **Reward Hacking Benchmark** (Thaman; arXiv 2605.02964, May 2026) | Six exploit categories with tool use; 13 models; 0–13.9 % exploit rates; environmental hardening cuts rates 88 % relative; 72 % of hacks come with an explicit rationale | Rationale-in-the-open matches our transcripts | No hidden ground truth, no loop |
| **ImpossibleBench** (LessWrong write-up, 2025–26) | Tasks made impossible so any pass is a hack | Cleanest "pass = cheat" design | Binary; no architecture comparison |
| **METR, Recent Frontier Models Are Reward Hacking (Jun 2025); Frontier Risk Report Feb–Mar 2026 (May 2026)** | ≥ 16 % of successful long-horizon runs involved cheating; Opus 4.6 attempted hacks in ~80 % of early MirrorCode attempts with tests hidden; scorer tampering, test extraction | Establishes the phenomenon at frontier scale | Field observations, not a controlled comparison; no iterated self-modification |
| ★ **The Verification Horizon: No Silver Bullet for Coding Agent Rewards** (Wang et al.; arXiv 2606.26300, Jun 2026) | Position + experiments: verification quality on scalability/faithfulness/robustness; test-, rubric-, user-, agent-based verification; "no fixed reward function stays effective as policy capability grows; verification must co-evolve" | Same thesis at industrial scale; their capability axis is our H6 | Large-scale RL, internal benchmarks; not a small controlled paired design with exact truth |
| ★ **Who Grades the Grader? Co-Evolving Evaluation Metrics and Skills** (Zhang et al.; arXiv 2607.12790, Jul 2026) | Co-evolved metric vs fixed judge/rubric; validated against hidden ground truth on locked test sets; removing anchor guards collapses the metric to always-pass; an independent judge caught metric gaming | Hidden ground truth + Goodhart demonstration + independent verification | Their variable is the evaluator's own evolution, not the information architecture of a fixed gate |
| **The Red Queen Gödel Machine** (Iacob et al.; arXiv 2606.26294, Jun 2026) | Recursive self-improvement with co-evolving evaluators; within-epoch fixed evaluation; reviewer bias found and corrected | RSI framing; evaluator as part of the loop | Optimises capability; does not measure proxy/truth drift under gates |
| **Proof-Carrying Cognition** (Reddy M, Karmakar; arXiv 2609.09776, Sep 2026) | "Verification gap"; reality-settled reward; learned verifiers collapse under pressure while sound ones improve; includes a pre-registered replication | Shared vocabulary; preregistration precedent in this area | Proposes a paradigm; no architecture comparison |
| **EvalSafetyGap** (arXiv 2606.30219, Jun 2026), **Self-Evolving Coding Agents** survey (Zhou et al.; arXiv 2608.03392, Aug 2026) | Surveys; the latter names "benchmark overfitting" and "patches that pass local checks" as open challenges and reports little systematic held-out evaluation in the surveyed loops | Confirms the gap this study addresses | — |
| **Dwork et al., Generalization in Adaptive Data Analysis and Holdout Reuse (2015)** | Reusable holdout; leakage bound per adaptive query | Our arm C is holdout reuse with an LLM as the adaptive analyst | Statistical learners; no LLM |
| Krakovna specification-gaming list; Skalse et al. 2022; Gao et al. 2023 (reward-model overoptimisation); Karwowski et al. 2023 (Goodhart in RL) | Foundations | Framing and vocabulary | — |

## What this leaves as the contribution

1. **Unit of analysis = the trajectory.** Twenty gated revisions of a self-modifying policy, with every proposal (accepted or not) scored on exact ground truth. The benchmarks above measure hack *rates per run*; nobody reports onset, drift slope, protective-vs-productive, or what the accepted lineage does over time.
2. **Paired, preregistered comparison of four verification architectures** (self, visible, +hidden holdout, +behavioural envelope + canaries) with the same optimiser and seeds. Verification Horizon argues this at scale; Who Grades the Grader varies the evaluator's evolution; no one varies the gate's *information* and *form* as the factor with everything else fixed.
3. **Mechanism decomposition** with exact truth: memorisation (V − V′), regularity exploitation (V′ − H), envelope drift — each separately measurable because the simulator defines the truth.
4. **A behavioural envelope as a gate type** (the descendant of the legacy auditor): a domain-grounded constraint on *form*, tested alongside constraints on *performance*. Not in any of the above.
5. **The no-LLM parametric baseline** under identical gates, which separates "what an optimiser can do in this family" from "what an LLM chooses to do".
6. **Monitorability with lead time** (five cheap signals vs a hidden-truth outcome), and **the recursive channel as a factor** (notes on/off).
7. **Pilot findings already in hand:** (a) no pressure, no Goodhart — an optimiser told only to "improve" holds at the honest ceiling; (b) with a release criterion, the same model special-cases the visible set and narrates it; (c) a hidden holdout scored on the proxy's metric inherits the proxy's blind spot (accuracy vs balanced accuracy at 20 % prevalence, −12 points G through the gate).

## How to frame it, and what not to claim

Frame as *an experiment on verification architecture*, not as *evidence that agents reward-hack* — the latter is established (METR, BAITBENCH, SpecBench) and reviewers will say so. Cite those as the motivation. Do not claim transfer to RL-trained reward hacking (this is in-context gaming by a fixed model), to models with situational awareness, or beyond the toy domain. Ten seeds bound the claims; report effect sizes with CIs, no p < .05 gates (F.4).

**Venues.** NeurIPS/ICLR safety and alignment workshops; SaTML; TMLR for a fuller version; arXiv + Alignment Forum for the audience that will actually use it. Zenodo first, per the Observer Zero pipeline.

**Housekeeping found by the search.** The GitHub repository's About text still reads "A validated self-improving (RSI) detector … with a clinical-compliance auditor that prevents reward hacking" — the pre-audit overclaim, and it is what search engines show. Replace it before anything is published.
