# FUTURE_DESIGN_PRECONDITIONS_NOTE

## Scope

This note is not a design. It is a guardrail sheet for the later RFC.

---

## Proven Preconditions For Design Work

- Structural regime truth is currently local, structural, bar-clocked, and symbol-scoped.
- Structural regime already has live downstream consumers with material decision impact.
- Detector output is already stabilized by hysteresis before emission.
- Aurora may apply a second internal anti-churn layer after detector emission.
- BTC influence already exists through anchor intake, `macro_resid`, and `anchor_shock_veto`.
- The active Aurora score path is quadratic and driven by `pillar_sum`, not by legacy linear-v2 surfaces.
- Assignment-first strategy activation already gives a clean fail-closed opt-in boundary.
- The runtime contract already distinguishes structural regime from potential future global/non-structural regime events.

---

## Unresolved Unknowns Blocking Clean Design

- Whether any hidden live consumer uses `macro_sync` for decisioning today.
- Whether any non-audited producer is expected to emit global execution regime events.
- What minimum additive observability fields are required so BTC-led context can be debugged without ambiguity.
- Whether a later additive layer should emit its own event or only annotate decision/strategy traces.

---

## Dangerous Assumptions That Must Not Be Carried Forward

- Do not assume there is no BTC influence today.
- Do not assume lifecycle semantics already exist because raw/stable regime and regime age exist.
- Do not assume typed config surfaces are live runtime surfaces.
- Do not assume `macro_sync` is the main current BTC path; the stronger proven path is `macro_resid` plus anchor veto.
- Do not assume future BTC-led logic can safely mutate structural regime without affecting forced-close, threshold, allowlist, and liveness semantics.
- Do not assume Aurora still relies on linear v2 scoring surfaces.

---

## Minimum Extra Evidence Needed Before RFC

- Explicit confirmation of whether any live policy consumes `macro_sync`.
- A decision on whether additive BTC context needs its own contract or can live inside existing decision traces.
- A concrete observability contract showing:
  - local structural regime
  - raw detector regime
  - Aurora effective regime if anti-churn is enabled
  - additive BTC context
  - final threshold/gating impact by source

---

## Guardrails For Later Design Discussion

- Preserve local structural regime as local truth unless a new contract is introduced.
- Keep any BTC-led effect additive-only, bounded, explainable, and fail-closed.
- Keep opt-in semantics outside the detector and aligned with assignment-first ownership.
- Do not let one BTC-led abstraction silently duplicate `macro_resid`, `anchor_shock_veto`, and threshold adaptation.
- Require explicit attribution fields before rollout, not after.
