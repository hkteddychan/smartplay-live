# SmartPLAY Live + PlayFinder — updated design

**Date:** 28 Nov 2026 (HKT)
**Status:** Proposal for a coding agent. Not implemented. Not a design-quality-gate pass.
**Repo:** [hkteddychan/smartplay-live](https://github.com/hkteddychan/smartplay-live)
**Live site (do not edit in this work):** https://hkteddychan.github.io/smartplay-live/
**App:** PlayFinder on branch `playfinder` (`com.playfinder.app`), not a separate repo

This is a third-party LCSD open-data mirror. Official product name on GovHK is「SmartPLAY 康體通」. Do not copy official branding, logos, or invent an official booking UI.

## Verdict

**Fail until implemented and re-audited.** The current public site still has broken strings, a missing stale state, and a table that hides venue / time / remaining slots on a 390-wide phone. The Android app already has a clearer list pattern and most of the required states; it should be tightened and visually aligned with the site, not redesigned.

Direction: **evolve the existing system**, do not replace it.

## Primary task

Help a Hong Kong person, in zh-HK, find a bookable LCSD slot: venue, date and time, and remaining places, then reach the official booking site.

Everything else (heatmap, watchlist, ads, ESP/device tools) is secondary.

## What stays

- Website information architecture: 設施餘額, 最新改變, 活動搜尋, plus the existing secondary tools (放場記錄, 放場分析, 裝置監察).
- Website filter model: 運動, 日期 chips, 地區 (including 淨係顯示有餘額 and the popover), 關鍵字, and the result table or its mobile equivalent.
- PlayFinder four-tab IA: 場地, 活動, 通知, 設定.
- Existing app behaviour: filter sheet, heatmap, availability pill, pull-to-refresh, last-sync / offline banner, loading / empty / error / not-synced / no-results, long-press watchlist, local WorkManager notifications, rewarded-video + 180s dwell gate, on-device distance sort, share sheet, official-site deep links.
- The current site green for Live / remaining-places, and amber only for 黃金時段 (prime time).
- AdSense on the site and AdMob in the app: placement may be adjusted so ads never cover filters or the first result; **IDs, applicationId, and the keystore do not change**.

## What changes

### Shared

- One typographic system: Noto Sans TC / system CJK, as the site already uses.
- Shared colour tokens in `tokens.css`. PlayFinder should use a **static** Material 3 scheme mapped to those tokens. Dynamic colour stays available as an optional Settings toggle, but it is **off by default** so the app does not drift into a generic device theme.
- Shared freshness language:
  - under 2 hours: `更新於 今天 14:23` (HKT)
  - 2 hours or older, data still shown: amber `資料可能已過時 · 更新於 26/11/2026 01:23` with a 重新整理 action
  - refresh failed, cache exists: `無法更新，以下係上次成功嘅資料` plus 重試
  - no cache: error state, not an empty table
- 黃金時段 uses the traditional character 黃 (the app currently writes `黄金時段`).
- `prefers-reduced-motion` / Android reduced-motion: no tab or sheet animation; pull-to-refresh may remain a short fade.
- High-frequency tab switches stay unaimated even when motion is allowed.

### Website

- Keep the filter-and-table on a 1440 and 768 viewport. On desktop, pin **場地** and **剩餘名額** so they stay in view when the table scrolls sideways.
- At a 390 viewport, replace the nowrap overflow table with **result cards**. Each card must show venue, date and weekday, time range, and remaining places **together**, without horizontal scrolling.
- Fix the two broken strings found in the 27 Nov 2026 audit:
  - 設施餘額 header no longer reads `0 揀咗幾多日` (default sort must not drop `rows._activeDates`).
  - 最新改變 weekday uses the same Hong Kong noon offset as the facility tab (`T12:00:00+08:00`), never `星期undefined`.
- Add a skip link, `<body>`, `<main>`, labels on every control, 44px targets, chips as `<button>` (not unlabelled `<span>`), Escape and click-outside to close the district popover, `color-scheme`, `theme-color`, and a favicon.
- De-emphasize operator「ESP View」: Chinese label「裝置監察」, under 更多 on narrow screens, never in the primary tab row.
- Footer: keep the unofficial-mirror disclaimer and the existing **私隱政策** link (`privacy/`, already on `main` as of 28 Nov 2026). Do not drop it.
- Do not rewrite privacy policy copy in this design.

### PlayFinder (Android)

- Keep list rows, not a new card grid. Tighten `SlotRow` so venue, time, and the availability pill cannot be pushed off-screen by a long venue name or the 黃金時段 badge.
- Replace “更新於 HH:mm” after the first hour with an absolute HKT datetime. Apply the same 2-hour stale treatment as the website.
- Settings already has a 私隱 card, but it points at repo file `PRIVACY.md`, which a Play user cannot open. Replace that line with a control that opens the live URL `https://hkteddychan.github.io/smartplay-live/privacy/`.
- Confirm every bottom-nav destination has a visible zh-HK label and a content description (場地 / 活動 / 通知 / 設定).
- Do not change AdMob unit IDs, `applicationId`, or signing.

## Visual system

The site already has a Primer-like utility look: light grey page, white panels, green selected chips, tight tables. Keep that product character. This is a live availability tool, not a marketing landing page, so Taste Skill “one section per screen / oversized hero” rules do not apply.

| Token | Light | Dark | Use |
| --- | --- | --- | --- |
| `--green` | `#0e8a3e` | `#3fb950` | Live, selected chip/tab, remaining > 0 |
| `--amber` | `#9a6700` | `#f0b429` | Stale data, 黃金時段 |
| `--danger` | `#cf222e` | `#ff7b72` | 滿額, failed refresh with no cache |
| `--bg` / `--card` / `--line` / `--text` / `--muted` | see `tokens.css` | see `tokens.css` | Surfaces and type |
| Selected control | green background, **white** text | green background, near-black text | Contrast on the selected chip |

Do not introduce a new teal, purple, or gradient brand. The app’s current static teal `#00696E` should move onto the shared green so web and APK read as one product.

## Website structure (unchanged IA)

```
[Skip] 跳到主要內容
Header   SmartPLAY Live    更新於 … / 可能已過時
Tabs     設施餘額 | 最新改變 | 活動搜尋 | 更多 ▾
Filters  運動 · 日期 · 地區 · 關鍵字 · 淨係顯示有餘額
Results  table (1440 / 768) or cards (≤700px)
Footer   unofficial disclaimer · 資料來源 · 私隱政策 · GitHub
```

「更多」contains 放場記錄, 放場分析, and 裝置監察 (formerly ESP View). On a 1440 viewport those three may remain visible as a quiet trailing group; they must not outrank the three primary tabs.

## App structure (unchanged IA)

```
Top app bar     場地 / filter / sort
Sync banner     fresh · stale · offline-with-cache
Heatmap         compact, existing behaviour
Slot list       venue + time + 剩餘名額
Bottom nav      場地 · 活動 · 通知 · 設定
```

## Before / After / Why

| Before | After | Why |
| --- | --- | --- |
| 設施餘額 shows `0 揀咗幾多日` because `applySort` clones the array and drops `rows._activeDates` | Count stays on the live `rows` object; header reads e.g. `12 個場地 · 揀咗 3 日` | The first line of the page is currently wrong; people cannot trust the rest of the data |
| 最新改變 shows `星期undefined` from `new Date(x.date + 'T00:00:00')` | Format weekdays with `T12:00:00+08:00`, same helper as the facility tab | A broken weekday on the changes tab makes the feed look unmaintained |
| 390-wide table is `nowrap` inside `overflow-x`, so venue, time, and 剩餘名額 are not visible together | Card rows at ≤700px; table only from 768 up, with sticky 場地 and 剩餘名額 | The primary task fails on a phone if those three facts are not in one glance |
| Header can read `26/11/2026 01:23` with no stale treatment after a missed refresh | Amber stale banner after 2 hours, plus a failed-refresh banner that still shows cache | Stale open-data without a warning is worse than an honest “last succeeded at” |
| `ESP View` sits in the main tab row in English | 「裝置監察」, under 更多 | Operator tooling should not compete with 搵場 |
| Chips are unlabelled `<span>`s; no skip link, no `<body>`, 32px targets, popover ignores Escape | Buttons, 44px targets, skip link, `<main>`, labelled inputs, Escape + click-outside | Keyboard, reader, and touch use of a public utility |
| Tab changes can feel animated | Immediate tab swap; honour `prefers-reduced-motion` everywhere else | High-frequency filter work should not wait on motion |
| App writes `黄金時段` | `黃金時段` | zh-HK typography; the simplified character is a product typo |
| App `更新於 01:23` after an hour hides the date | Absolute HKT datetime, and the same 2-hour stale rule as the site | A clock time without a date repeats the website’s stale-header problem |
| App default dynamic colour (API 31+) | Static shared tokens; optional dynamic colour in Settings | Stops the app looking like a generic Material sample, and keeps it aligned with the site |
| Settings 私隱 card points at repo file `PRIVACY.md` | Settings → 私隱政策 opens the live HTTPS URL | A Play user cannot open a file inside the repo |
| Wordmark is a 🎯 + text | Typographic wordmark, “Live” in green; modest favicon | The emoji mark reads as a demo, not a product |

## Required states (both surfaces)

Must be designed and later implemented:

1. Loading (first sync and pull-to-refresh)
2. Fresh data
3. Stale data (≥ 2 hours), results still shown
4. Refresh failed, cache exists
5. Refresh failed, no cache
6. Filters yield no results (distinct from empty / not-synced)
7. App not-yet-synced (PlayFinder already has this)
8. Official booking / share actions on a row
9. District popover open, dismissed with Escape or outside click (web)
10. Reduced-motion

See the HTML mockups: use the prototype state switcher at the top of each file.

## References actually used

- Rendered SmartPLAY Live, light scheme, 27 Nov 2026 audit screenshots under `/workspace/smartplay-audit/shots/` (1440, 768, 390). Dark scheme and live reduced-motion were **not** previewed on the public site.
- Current `index.html` from the 27 Nov audit copy (`/workspace/smartplay-audit/home.html`).
- PlayFinder source on `playfinder` (tip then `d3f4c21`), including `HomeScreen.kt`, `Theme.kt`, `docs/designs/`, and `EXPORT_FOR_AGENTS.md`. **The APK itself was not installed or screenshot.** This app portion is source-based, not a rendered-device review.
- Live privacy page, verified HTTP 200 on 28 Nov 2026 01:57 HKT: https://hkteddychan.github.io/smartplay-live/privacy/
- GovHK SmartPLAY HTML patterns already cited in the audit (skip link, 私隱政策). The official booking UI at `https://www.smartplay.lcsd.gov.hk/website/tc/index.html` previously returned HTTP 405 and was **not** used as a visual reference. Do not invent it.

## Skills actually read

- `design-quality-gate` (shared skill)
- Anti UI Slop: `SKILL.md`, `reference/audit.md`, `reference/operate.md` (dashboard / product path)
- Taste Skill: `SKILL.md`, `references/gate.md` (utility dashboard; hero/one-section house rules only partly apply)
- Emil Design Engineering: `SKILL.md`
- Vercel Web Design Guidelines: `SKILL.md`, `references/command.md`
- ThinkUI principle (no local file; paid MCP not connected): only real shipped UI, sources named above; no invented official 康體通 screens

## Out of scope

- Implementing or merging this proposal
- Editing GitHub Pages or `main`
- Rewriting privacy policy wording (Play Console copy alignment is a compliance issue, not a visual rewrite)
- Changing AdMob / AdSense account IDs, `applicationId`, or the keystore
- New sports, new booking flow, or a marketing landing page
- Subscribing to paid design MCPs
