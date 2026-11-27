# SmartPLAY Live and PlayFinder — design proposal (28 Nov 2026)

This folder is a **design proposal only**. It is not a ship decision, not a quality-gate pass, and not an implementation.

Start here:

1. [PROPOSAL.md](./PROPOSAL.md) — direction, shared system, screens, states, and required changes
2. [IMPLEMENTATION.md](./IMPLEMENTATION.md) — coding handoff, file-level fixes, and what not to touch
3. [tokens.css](./tokens.css) — shared colour, type, and motion tokens
4. Open the HTML mockups in a real browser:
   - [web/facility.html](./web/facility.html) — website (resize to 1440, 768, and 390)
   - [apk/app.html](./apk/app.html) — PlayFinder Android frames

A simple favicon mark is in `assets/favicon.svg`.

Prototype chrome at the top of each mockup (state switchers) is not part of the product.

## Constraints

- Do not merge this into `main` until a coding agent implements the work on a separate branch.
- Do not change GitHub Pages, AdMob IDs, the application id, or the keystore.
- Do not rewrite the live privacy policy text; link it from the website footer and from Settings.
- Keep the existing filter-and-table (web) and list-and-filter-sheet (app) systems. This is an update, not a new product look.

Privacy URL (live as of 28 Nov 2026 01:57 HKT, HTTP 200): https://hkteddychan.github.io/smartplay-live/privacy/
