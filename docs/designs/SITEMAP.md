# SmartPLAY — Design Artifact Index

This directory follows the EGM (Elephant-Goldfish Model) layout: design
documents live in `docs/designs/`, and review reports live in
`docs/designs/reviews/`.

## Android app — PlayFinder

| Artifact | Purpose | Status |
|---|---|---|
| [2026-11-26-playfinder-android.md](./2026-11-26-playfinder-android.md) | Approved design spec for the PlayFinder Android app | Approved 2026-11-26; reviewed 2026-11-27 |
| [2026-11-26-playfinder-android-plan.md](./2026-11-26-playfinder-android-plan.md) | 14-task implementation plan derived from the spec | Executed 2026-11-26/27 |
| [reviews/](./reviews/) | Goldfish review stage reports (zoom-out, comprehension, critic, implementation readiness, consolidated) | 2026-11-27 |
| [2026-11-27_DRIFT_REPORT.md](./2026-11-27_DRIFT_REPORT.md) | Doc-vs-code drift baseline (pre-fix; superseded by the re-baselined spec) | 2026-11-27 |
| [../formal/PlayFinder.lean](../formal/PlayFinder.lean) | Lean 4 statement of the grant-expiry and list-length invariants (not compiled by CI) | 2026-11-27 |
| [../AUDIT.md](../AUDIT.md) | Build/test evidence, defect log, UI/UX change log | Updated 2026-11-27 |

Code contracts (per-package `README.md` with Interface / Invariants / Side
Effects) live next to the code they describe, under
`app/src/main/java/com/playfinder/app/`.

## Website — SmartPLAY Live

| Artifact | Purpose | Status |
|---|---|---|
| [../specs/2026-11-26-smartplay-live-rebuild-design.md](../specs/2026-11-26-smartplay-live-rebuild-design.md) | Website rebuild design (LCSD mirror, ntfy alerts, AdSense) | Separate product; not covered by the PlayFinder review |

## Review protocol used here

1. **Bootstrap** — every package gets a `README.md` contract with the public
   interface, the invariants the code relies on, and the side effects it
   performs.
2. **Drift report** — `docs/designs/YYYY-MM-DD_DRIFT_REPORT.md` compares every
   design document with the current source and lists only the divergences.
3. **Goldfish review** — fresh-context reviewers (no conversation history)
   audit the design in five stages: initial zoom-out, comprehension, critic,
   intermediate zoom-out, implementation readiness. Each stage report lands in
   `docs/designs/reviews/`.
4. **Resolve** — findings are classified as fix-now, fix-in-doc, or accepted
   trade-off with a written reason. Code and documents are updated to match.
5. **Loop** — the drift report and a verification reviewer are re-run after the
   fixes so nothing stays unaddressed.

## Artifacts outside this directory

- `docs/AUDIT.md` — build and test evidence, defect log, UI/UX change log.
- `docs/formal/PlayFinder.lean` — Lean 4 statement of the invariants.
- `PRIVACY.md` — the published privacy policy.
- `app/src/main/java/com/playfinder/app/**/README.md` — the per-package
  contracts (Interface / Invariants / Side Effects).
