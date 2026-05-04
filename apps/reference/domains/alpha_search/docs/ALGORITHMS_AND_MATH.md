# Alpha Search Algorithms and Math

This document covers the scoring families currently housed under alpha_search.

It is not the authority for runtime topology, judge ownership, or simulator wiring. Use ATLAS.md and ARCHITECTURE.md for that. This page is only about the main scoring formulas and how they relate to current code.

## 1. Scoring Families in the Current Tree

alpha_search currently contains three math surfaces:

1. Aurora adapter scoring, which delegates to the shared QuadraticScoringKernel
2. TA-model and ensemble scoring under the classic alpha-model path
3. judge expert scoring formulas used only in the shadow evidence line

## 2. Aurora Adapter

AuroraAlphaAdapter is not an independent strategy formula. It is a read-only wrapper around the same pure scoring kernel used by live Aurora.

Its role inside alpha_search is:

- accept the alpha_search feature snapshot
- validate essential features and price availability
- call QuadraticScoringKernel.compute(...)
- translate the kernel result into AlphaScore

That is why the exact Aurora scoring math is not duplicated here. The kernel remains the formula authority, and alpha_search is the wrapper that reuses it in shadow and replay contexts.

## 3. Ensemble Combination

EnsembleModel combines multiple AlphaScore values into one aggregate score.

The main combination idea is the weighted average:

$$
S_{ensemble} = \frac{\sum_i w_i s_i}{\sum_i w_i}
$$

and the same weighted aggregation is used for confidence:

$$
C_{ensemble} = \frac{\sum_i w_i c_i}{\sum_i w_i}
$$

Under the current implementation this is documented under non-negative weighting assumptions. The ensemble starts from equal positive weights, applies non-negative min and max bounds, and renormalizes after rebalancing.

where:

- $w_i$ is the current model weight
- $s_i$ is the model score
- $c_i$ is the model confidence

The implementation also tracks performance history, optional objective feedback, and periodic rebalancing. The important current-tree point is that ensemble math remains one provider family inside alpha_search, not the full definition of the domain.

## 4. Classical TA Models

The classic TA path still contains momentum, mean_reversion, and volatility models. Those models continue to return AlphaScore values and can be combined through EnsembleModel.

These models are still part of the domain, but they are no longer sufficient to describe alpha_search as a whole because the current tree also contains the Aurora adapter path, judge experts, and the simulator subtree.

## 5. Judge Expert: Signal Weights

SignalWeightsExpert revives the legacy weighted-centering formula as a pure scoring expert:

$$
score = \frac{\sum_f w_f \cdot (x_f - n_f)}{\sum_f |w_f|}
$$

where:

- $x_f$ is the observed feature value
- $n_f$ is the configured neutral value
- $w_f$ is the configured feature weight

The final verdict direction is thresholded from this score:

- $score > threshold$ means LONG
- $score < -threshold$ means SHORT
- otherwise the result is NEUTRAL

This expert returns AlphaScore only. The later bridge into judge evidence and verdict artifacts happens in the plugin path, not in the formula itself.

## 6. Judge Expert: Feature Neutrals

FeatureNeutralsExpert uses a two-part direction-strength composite.

Directional score:

$$
dir = \frac{\sum_f w^{dir}_f \cdot (x_f - n_f)}{\sum_f |w^{dir}_f|}
$$

Strength score:

$$
str = \frac{\sum_f w^{str}_f \cdot (x_f - n_f)}{\sum_f |w^{str}_f|}
$$

Then the strength component is clamped and applied multiplicatively:

$$
final = dir \cdot (1 + \alpha \cdot clamp(str, 0, strength\_cap))
$$

This keeps directional sign and uses strength as an amplifier. As with SignalWeightsExpert, the formula is pure scoring only and does not itself emit judge events.

## 7. Fail-Closed Math Semantics

The current tree uses fail-closed behavior as part of the mathematical contract:

- missing essential inputs produce neutral or unknown AlphaScore results instead of widening behavior silently
- Aurora adapter fail-closes on missing price, missing essential features, or kernel errors
- judge experts fail-close to zero-confidence unknown outputs when required features are absent
- the plugin may emit a neutral alpha event for standard providers or suppress generic emission for judge experts

This fail-closed posture is part of the domain design, not just an implementation detail.
