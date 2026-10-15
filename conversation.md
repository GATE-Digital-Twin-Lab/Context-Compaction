# Research Notes: Reliable Context Compaction with Risk Control and PPI

*Summary of a discussion, October 14, 2026*

---

## 1. Background: Prediction-Powered Inference (PPI)

**Paper:** Angelopoulos, Bates, Fannjiang, Jordan, Zrnic, *Prediction-Powered Inference* (arXiv:2301.09633).

### The problem
We want a confidence interval for a population quantity θ* (mean, median, regression coefficient). We have:
- a **small gold-standard set** of n labeled examples (expensive, trustworthy);
- a **large unlabeled set** of N ≫ n examples, for which an ML model gives cheap predictions f(X).

Two naive approaches:
- **Imputation:** treat predictions as truth. The interval is narrow but biased; in the paper it missed the true value in every experiment.
- **Classical:** use only the gold set. Valid but wide.

### Core trick (mean estimation)
θ̂_PP = (1/N) Σ_unlabeled f(X̃_i) − (1/n) Σ_labeled (f(X_i) − Y_i)

The second term is the **rectifier**: the model's average error, measured on the gold set and subtracted. The estimate is unbiased regardless of model quality.

Width of the interval:
- noise from the big-set average (tiny, since N is huge);
- noise in the rectifier, which depends on how much the **model's errors vary**, not on how much the outcomes vary.

So a good model gives a narrower interval. A consistently biased model is fine; erratic errors hurt.
Analogy: a cheap bathroom scale that reads 2 kg heavy. Weigh everyone on it, check a few people on an accurate scale, and subtract the difference.

### General case (Section 2)
Many estimands are "balance points": minimizers of an average loss, where the average gradient equals 0.
PPI computes the gradient from predictions on the big set, corrects it with a rectifier
(gradient with true labels minus gradient with predictions, measured on the small set),
and keeps every θ for which the corrected gradient could plausibly be 0. That's why
Algorithms 2, 3 and 5 loop over a grid of candidate values.
For the median or a quantile, the rectifier at θ is P(Y ≤ θ) − P(f(X) ≤ θ).

### Results
Labels needed to reach a firm conclusion, PPI vs classical: galaxies 189 vs 449,
AlphaFold proteomics 316 vs 799, deforestation 21 vs 35, income regression 177 vs 282.

### Limits (Appendix G)
- PPI helps only if N ≫ n and the model is accurate enough that its errors vary less than the outcomes.
- For binary outcomes with p = 0.5, the model error must be below about 25%; for p = 0.1, below about 9.5%.
  **The rarer the event, the more accurate the model must be.**
- A weak model can make PPI worse than classical inference. **PPI++** adds a tuning weight that fixes this.

### Applications
- In the paper: proteomics (AlphaFold), astronomy (galaxy classification), genomics, remote sensing
  (deforestation), census analysis, ecology (plankton). Talks also mention electronic voting.
- Later work:
  - LLM evaluation with LLM judges plus a few human labels (Stratified PPI, NeurIPS 2024;
    PRECISE for ranking metrics);
  - social science with LLM text annotations (Confidence-Driven Inference, NAACL 2025;
    related DSL framework by Egami, Stewart et al.);
  - clinical trials with prognostic models;
  - biological sequence design.
- Python package: `ppi_py`.

---

## 2. The Research Idea: Risk-Controlled Context Compaction plus PPI

### Where PPI fits
- **Learn-then-Test (LTT):** for each compaction level λ, test H_λ: R(λ) > α using calibration data.
  The bottleneck is gold labels (is the needed information still there?).
- **PPI's role:** make each per-λ test more powerful by combining a few gold-labeled examples
  with many cheaply scored ones.
- **Prior work combining the two methods:** Einbinder, Ringel, Romano,
  *Semi-Supervised Risk Control via Prediction-Powered Inference* (arXiv:2412.11174).
  So **the combination itself is not novel**; novelty must come from the setting.

### Three possible loss definitions
1. **Correctness against ground truth.** Gold = human-verified correctness.
   Proxy = agreement with the full-context answer.
2. **Fidelity to the full context.** L = 1{answer from compacted context ≠ answer from full context}.
   Only needs PPI if judging equivalence is expensive.
3. **Evidence retention (chosen).** Gold = human annotation of the needed units.
   Proxy = LLM annotation.

### Evidence retention: one number per example
Units C = {e_1, …, e_m}, scores s(e, q) ∈ [0, 1] (lower = more relevant).
C_λ(q) = { e ∈ C : s(e, q) ≤ λ } (nested; larger λ keeps more).

L(q, λ) = 1{ E*(q) ⊄ C_λ(q) }

**Critical threshold:** τ(q) = max over e ∈ E*(q) of s(e, q). Then L(q, λ) = 1{ τ(q) > λ }, and
R(λ) = P(τ > λ).

- One annotation gives the loss at **every** λ.
- Risk control reduces to bounding a quantile of τ.
- **Classical solution:** split conformal quantile of the gold τ values.
- **PPI solution:** the paper's quantile algorithm (Algorithm 2), using τ̂ from an LLM annotator.
- Scanning λ in a fixed order is fixed-sequence testing, so there is no multiple-testing penalty.

**Redundancy** (the same fact appears in several units): annotate facts F_j, each with the set S_j of
units that state it. With "lower score = more relevant":
τ = max over facts j of ( min over u ∈ S_j of s(u) ).
Still one scalar per example.

**Choice of knob:** a raw score threshold, or a budget (keep the top b units or tokens).
The budget version is often more interpretable, and it is robust to score scales that differ
between contexts.

### What the proxy must get right, and the main danger
- The rectifier term 1{τ > λ} − 1{τ̂ > λ} is zero whenever gold and proxy fall on the same side of λ.
  So the LLM only needs to get examples **near the cut** right.
- **Danger:** at α = 5%, failures are rare events. The judge must disagree with the gold label less
  than about 5% of the time near the cut, or PPI won't help. Use PPI++ weighting.
  This is the main empirical question of the project.

### Technical pitfalls
- **Use LTT, not conformal risk control.** The PPI estimate can be negative or non-monotone;
  LTT only needs valid p-values.
- **Use finite-sample (non-asymptotic) PPI intervals** (paper's Appendix C, betting-based),
  because n is small.
- **The LLM annotator must not be tuned on the gold calibration set.**
- **The guarantee is marginal:** averaged over conversations, not per conversation.
- **Calibration data must match deployment.**
- **Run a sufficiency check on gold labels:** feed only the annotated evidence to the model
  and confirm it can answer. Missing *alternative* evidence makes you conservative (safe);
  missing *essential* evidence makes the guarantee invalid.

### Toy example
Six chat turns with scores. The question needs turns u2 (budget, 0.70), u3 (trains, 0.50) and
u5 (dates, 0.90). In the "higher = more relevant" convention used in the example, τ = 0.5,
and λ above 0.5 drops u3.
- With 10 human-labeled τ values and α = 20%, conformal picks the 2nd-smallest τ.
  That's valid but conservative.
- The LLM labels 1,000 more examples. If, on the 10 human-labeled ones, the LLM undercounts
  failures by 0.1, add 0.1 to the LLM's estimate on the big set.
- **No LLM is needed for the loss itself** in extractive compaction (it's a set check).
  The LLM is only the cheap annotator for PPI.

---

## 3. Datasets

**Single questions with evidence labels:**
- **LongMemEval:** 500 questions, turn-level `has_answer` flags, ~115k-token histories,
  oracle version available. Evidence is LLM-generated and inserted among filler sessions,
  which may make it easier than real chats.
- **LoCoMo:** 10 conversations (~300 turns, ~9K tokens each), ~2,000 QA pairs with evidence
  dialog IDs. Query-agnostic, but only 10 independent conversations, so the effective sample
  size is about 10.
- **MuSiQue:** ~25K questions with 2–4 hops, 20 paragraphs each, 2–4 gold.
  The decomposition maps sub-questions to supporting paragraphs. Best for simulation studies.
- **QASPER:** 5,049 questions over 1,585 NLP papers, evidence paragraphs and highlighted
  sentences, multiple annotators (real redundancy).
- **HotpotQA:** sentence-level supporting facts; known to be noisy.

**Dependent follow-up questions:** Doc2Dial / MultiDoc2Dial (per-turn grounding),
CoQA / QuAC (short passages), ConvFinQA (financial, expert-like).
Verify the annotation details before use.

**Plan:** develop on MuSiQue, main results on LongMemEval or dialogue datasets, QASPER for long documents.

---

## 4. Relation to My Prior Work (LTT-RAG)

**LTT-RAG:** retrieve from a known corpus so that answer-bearing documents are retrieved with
probability at least 1−α₁; re-rank and filter so relevant ones are kept with probability at least
1−α₂. Single-turn, query-aware, gold labels for every question.

**Risk:** "LTT-RAG + PPI" looks incremental, especially since PPI+LTT already exists (Einbinder et al.).

**Test for novelty:** *what question can this paper answer that LTT-RAG cannot?*

**Directions considered:**
1. Query-agnostic compaction for conversations (**chosen**).
2. Label-efficient recalibration in new domains (an honest reason for label scarcity).
3. Making PPI work for rare-event risks (active labeling, stratification, analysis of when it helps).
4. Abstractive compaction.
- Fallback: a journal extension of LTT-RAG.

| | LTT-RAG | New project |
|---|---|---|
| When filtering happens | After the question is known | Before any future question is known |
| What is guaranteed | Each question, independently | A whole conversation |
| Operation | Retrieve and filter | Compact (discard, possibly rewrite) |
| Gold labels | Abundant | Scarce |

---

## 5. The Chosen Setting

### Assumptions
- **Expert assistant.** Future questions are in-distribution: their evidence exists in the
  pre-compaction context.
- **The expert's agenda drives the question sequence,** not the system's answers.
  Compaction does not change which questions are asked.
- **Scenario:** the expert converses with the LLM; at a length threshold the history is compacted
  **once**; the conversation continues.
- **The most recent turns may be kept verbatim** (always kept; λ applies only to older turns).
- Multiple rounds of compaction are future work.

### Conversation as the unit of the guarantee
E*_conv = union over t of E*(q_t)
L_conv(λ) = 1{ E*_conv ⊄ C_λ }
τ_conv = max over t of τ(q_t)

- **Dependence between turns is handled** by treating (context, conversation) as the i.i.d. sample.
- **Two risk choices:** P(any turn fails), which is stricter and recommended for experts,
  or the average fraction of failed turns.

### Beyond discarding: facts and entailment
L(q, λ) = 1{ some needed fact f ∈ F*(q) cannot be inferred from the compacted context }

- **Discarding is the special case** where "inferred" means "the unit is present."
- **Rewriting needs entailment judgments** at every compression level. Gold labels become
  genuinely scarce, an LLM entailment judge is the natural proxy, and PPI becomes necessary.
- **Tiered compaction:** keep verbatim / summarize / drop, with two thresholds calibrated jointly
  (multi-parameter LTT).

### Candidate contribution statement
> We provide the first distribution-free guarantee that a context compacted before future questions
> are known retains the information needed for an entire conversation, covering extractive and
> abstractive compaction, with calibration made practical through prediction-powered inference.

---

## 6. "Is This Really Necessary?" (Answering Reviewers)

### Core argument: compaction fails silently
The model doesn't know a fact is gone, and it answers confidently. The expert believes the system
remembers what they said.
Example: a penicillin allergy is mentioned in turn 4, compaction happens at turn 40, and amoxicillin
is recommended in turn 52, with no warning.

### Supporting arguments
- **Compaction is already deployed** in assistants and coding agents, using fixed heuristics and
  no known failure rate.
- **Reliability and efficiency together:** fixed settings are either unsafe or wasteful depending on
  the domain. Calibration gives the most compression that still meets the promise.
- **Auditable error rates for expert domains:** "essential information lost in at most 2% of sessions,
  with 95% confidence."
- **PPI makes per-deployment recalibration cheap.**

### Key experiments
1. Show that existing compaction methods lose needed information at varying rates, and that the
   failures are silent (confident answers). This is the motivating figure.
2. Show that fixed settings are unsafe in some domains and wasteful in others, while the calibrated
   method hits the target everywhere.
3. Compare against the full context: cost, latency, accuracy (long contexts degrade quality).
4. Measure label efficiency with PPI.

### Objections and responses
- **"Context windows keep growing."** Cost and latency still grow, quality degrades on long inputs,
  and sessions are unbounded.
- **"Retention ≠ correctness."** This is intentional: the guarantee isolates the harm caused by
  compaction. Report answer accuracy alongside.
- **"The guarantee is marginal."** State it plainly as a limitation.
- **"It assumes calibration matches deployment."** That is exactly why cheap recalibration via PPI matters.

---

## 7. Branching Conversations (Same History, Different Continuations)

The guarantee averages over futures. One branch can fail while another succeeds; the failing branch is
one of the allowed α failures.

- **Conditional risk:** r(H, λ) = P(failure | history H)
- **Controlled quantity:** R(λ) = E_H[ r(H, λ) ] ≤ α. Individual histories can exceed α.

**Compaction should keep facts in proportion to how likely future questions are to need them.**

### Three levels of promise
1. **Marginal** (current): at most α of sessions fail.
2. **Conditional on the type of conversation:** calibrate per group (domain, length, task).
   See Gibbs, Cherian, Candès, *Conformal Prediction with Conditional Guarantees*.
3. **Worst case over all continuations:** keeps almost everything, so no compression.
   Useful as the boundary that justifies a probabilistic promise.

**Hybrid:** always keep explicit constraints (allergies, deadlines, decisions); apply the
probabilistic guarantee to the rest.

### Calibration implications
- **The sampling unit is the history.** Average the losses over its continuations
  (still in [0, 1], so LTT and PPI apply).
- **Several continuations per history** estimate r(H, λ) directly. Report the **distribution**
  of conditional risk, not just its mean.
- **Continuations must come from real experts.** LLM-simulated questions change what the guarantee
  covers; PPI fixes label errors, not differences in which questions get asked.

---

## 8. Project Overview (Current Draft)

### Reliable Context Compaction with Semi-Supervised Risk Control via Prediction-Powered Inference

The project combines Learn-then-Test (LTT) and Prediction-Powered Inference (PPI) to compact an LLM's
context while keeping the risk of losing needed information below a chosen level α.

**Setup.** A context is split into units C = {e_1, …, e_m}. For a query q, the units needed to answer
it are E*(q) ⊆ C. A scoring function s(e, q) ∈ [0, 1] rates each unit (lower = more relevant).
For a threshold λ:

$$C_\lambda(q) = \{\, e \in C : s(e, q) \le \lambda \,\}$$

Smaller λ means more compaction.

**Loss and risk.**

$$L(q, \lambda) = \mathbb{1}\{\, E^*(q) \not\subseteq C_\lambda(q) \,\}, \qquad R(\lambda) = \mathbb{E}_q\big[L(q, \lambda)\big]$$

**Goal.** Find the smallest λ such that, with probability at least 1 − δ, R(λ̂) ≤ α.
LTT tests each candidate λ from largest to smallest and stops at the first one whose risk cannot be
shown to be below α.

**LLM as a cheap labeler.** Human-annotated E*(q) is available only for a small set Q (|Q| = n).
An LLM produces approximate sets Ê(q) for a large set Q' (|Q'| = N ≫ n) and for Q:

$$\hat L(q, \lambda) = \mathbb{1}\{\, \hat E(q) \not\subseteq C_\lambda(q) \,\}$$

$$\hat R_{PP}(\lambda) = \frac{1}{N} \sum_{q \in Q'} \hat L(q, \lambda) + \frac{1}{n} \sum_{q \in Q} \big( L(q, \lambda) - \hat L(q, \lambda) \big)$$

The first term is the LLM estimate; the second is the correction. The correction removes the LLM's
bias, so the estimate stays valid even when the LLM makes mistakes. A more accurate LLM gives a
tighter estimate and allows more aggressive compaction.

**Note:** the pooled formula 1/(|Q|+|Q'|) Σ over Q ∪ Q' is **wrong**. The true loss can't be computed
on Q', and substituting the LLM's loss reintroduces its bias. Keep the two sets separate, as above.

---

## 9. Open Decisions and Next Steps

- [ ] Extractive only, or include abstractive / tiered compaction (facts and entailment)?
- [ ] Risk definition: P(any turn fails) vs average fraction of failed turns.
- [ ] Marginal vs group-conditional guarantee; a must-keep category for explicit constraints?
- [ ] Choose datasets with dependent follow-up questions; verify annotation completeness
      (sufficiency check).
- [ ] Get or construct multiple real continuations per history.
- [ ] Motivating experiment: failure rates and silence of existing compaction methods.
- [ ] Test whether an LLM annotator is accurate enough near the cut for small α (the PPI viability question).
- [ ] Later: multiple compaction rounds and end-to-end calibration.

### Key references
- Angelopoulos et al., *Prediction-Powered Inference* (2023)
- Angelopoulos, Duchi, Zrnic, *PPI++* (2023)
- Angelopoulos et al., *Learn then Test* (arXiv:2110.01052)
- Einbinder, Ringel, Romano, *Semi-Supervised Risk Control via PPI* (arXiv:2412.11174)
- Zrnic, Candès, *Active Statistical Inference* (2024)
- Gibbs, Cherian, Candès, *Conformal Prediction with Conditional Guarantees*
- Fisch et al., *Stratified PPI for Hybrid LM Evaluation* (NeurIPS 2024)
- Conformal context filtering for RAG (arXiv:2511.17908); CARE for medical summarization (arXiv:2606.08969)