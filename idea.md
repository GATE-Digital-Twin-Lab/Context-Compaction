# Reliable Context Compaction with Semi-Supervised Risk Control via Prediction-Powered Inference

## Overview

The project combines Learn-then-Test (LTT) and Prediction-Powered Inference (PPI)
to compact an LLM's context while keeping the risk of losing needed information
below a chosen level $\alpha$.

### Setup

A context is split into units $C = \{e_1, \dots, e_m\}$. For a query $q$, the
units needed to answer it are $E^*(q) \subseteq C$.

A scoring function $s(e, q) \in [0, 1]$ rates each unit (lower = more relevant).
For a threshold $\lambda$, the compacted context keeps every unit scoring at most
$\lambda$:

$$C_\lambda(q) = \{\, e \in C : s(e, q) \le \lambda \,\}$$

Smaller $\lambda$ means more compaction.

### Loss and risk

Compaction fails on $q$ if any needed unit is dropped:

$$L(q, \lambda) = \mathbb{1}\{\, E^*(q) \not\subseteq C_\lambda(q) \,\}$$

The risk is the probability of failure over queries:

$$R(\lambda) = \mathbb{E}_q\big[L(q, \lambda)\big]$$

### Goal

Find the smallest $\lambda$ such that, with probability at least $1 - \delta$,

$$R(\hat\lambda) \le \alpha$$

LTT does this by testing each candidate $\lambda$, from largest to smallest, and
stopping at the first one whose risk cannot be shown to be below $\alpha$.

### Using an LLM as a cheap labeler

Human-annotated $E^*(q)$ is available only for a small set $Q$ ($|Q| = n$).
An LLM produces approximate evidence sets $\hat E(q)$ for a large set $Q'$
($|Q'| = N \gg n$) and for $Q$, giving the proxy loss:

$$\hat L(q, \lambda) = \mathbb{1}\{\, \hat E(q) \not\subseteq C_\lambda(q) \,\}$$

PPI estimates the risk using the LLM labels on $Q'$, corrected by the LLM's
measured error on $Q$:

$$\hat R_{PP}(\lambda) =
\underbrace{\frac{1}{N} \sum_{q \in Q'} \hat L(q, \lambda)}_{\text{LLM estimate}}
\; + \;
\underbrace{\frac{1}{n} \sum_{q \in Q} \big( L(q, \lambda) - \hat L(q, \lambda) \big)}_{\text{correction}}$$

The correction removes the LLM's bias, so the estimate stays valid even when the
LLM makes mistakes. The more accurate the LLM, the tighter the estimate, and
the more aggressively the context can be compacted.