# Implementation handoff

For the coding agent that follows this proposal. Design only is already done; this document says what to change in the repo, and what not to touch.

Line numbers refer to `index.html` on `main` as of the 27 Nov 2026 audit copy (and a 28 Nov 2026 re-check of `main`). **Re-confirm lines before editing** if `main` has moved.

Work on a **separate implementation branch**. Do not merge this design branch, do not commit product changes into the design branch, and do not change GitHub Pages.

Suggested branch names:

- Design (this upload): `design/2026-11-28-web-apk`
- Web implementation, from `main`: `fix/web-design-2026-11-28`
- App implementation, from `playfinder`: `fix/apk-design-2026-11-28`

Keep web and app work on those two bases. Do not mix this work into the privacy page, Play Console copy, or other feature branches.

## Do not touch

- GitHub Pages settings, the live site, or a direct commit to `main`
- `privacy/index.html` wording (the page is already live; only keep linking to it)
- AdSense client `ca-pub-2824936620876447`
- AdMob unit IDs, `applicationId` `com.playfinder.app`, signing / keystore
- Official booking deep-link behaviour (open the official site / TC URL; do not invent a booking UI)
- New sports, new IA, or a marketing landing page

## Website (`index.html` on `main`)

### Bugs (must fix first)

1. **`0 揀咗幾多日`** — `bindSort('#f-table', renderFacility, null, 'c6', 'desc')` around `:985` makes `applySort` (`:867-871`) clone the array and drop `rows._activeDates`, so `nDates` at `:1269` is 0. Preserve the property, or count `selDates.size` (or the selected date chips) after sort. The header should stay truthful, e.g. `12 個場地 · 揀咗 3 日`.
2. **`星期undefined`** on 最新改變 — `:1346-1348` uses `new Date(x.date + 'T00:00:00')`. Use the same HKT helper as the facility tab (`weekdayCN` at `:914-916`, which already uses a noon +08:00 offset). Never concatenate `'星期' + undefined`.
3. **Stale / failed refresh** — the header `#upd-time` and the 3-second `#update-banner` (`:99-113`, `:1821-1822`) are not a stale state. If the last successful payload is ≥ 2 hours old, show an amber persistent banner: `資料可能已過時 · 更新於 …` with 重新整理. If a refresh fails and cache exists, keep the rows and show `無法更新，以下係上次成功嘅資料` plus 重試. If there is no cache, show an error, not an empty table. Use an absolute HKT datetime, not time-only.

### Layout

4. **390 viewport** — `th, td` are `white-space: nowrap` (`:52`) inside `.table-wrap` overflow (`:179-180` and the other tables). At `max-width: 700px`, render 設施餘額 (and the other result lists if they have the same problem) as **cards**: venue, date + weekday, time range, remaining places, all visible without sideways scrolling.
5. **768 and 1440** — keep the table. Make **場地** and **剩餘名額** sticky so sideways scroll does not hide the primary facts.
6. **Tabs** — keep 設施餘額, 最新改變, 活動搜尋 as the primary trio. Move 放場記錄, 放場分析, and ESP View into a 更多 control on narrow viewports. Rename `ESP View` (`:129`) to「裝置監察」. Tab switches must be immediate (no animation).

### Accessibility and polish (Vercel, file:line)

- `:117-454` (structure) — no skip link, no `<main>`, and still no `<body>` start tag after `</head>` (re-checked 28 Nov: `</head>` is followed by `<div class="container">`). Add `跳到主要內容`, wrap results in `<main>`, and add `<body>`.
- Date / period / sport chips are `<span class="chip">`, not buttons. Make them `<button type="button">` with pressed/selected state.
- `#f-time` (`:170`) has no accessible name. Associate a visible `<label>` (or `aria-label`) with every input, including 關鍵字 and 地區.
- Enlarge tap targets to at least 44×44px (chips are ~31px; 全部/清除 ~42×23; checkbox is smaller).
- District popover: close on Escape and on click outside.
- `:99-113` — `#update-banner` and `.spinner` ignore `prefers-reduced-motion`. Under `reduce`, no `translateY`, no spinner rotation; show and hide instantly or with opacity only.
- Add `color-scheme`, a `theme-color` that matches `--green`, and a simple favicon (no 🎯 as the only mark).
- Selected chips/tabs: green background with **white** text in light scheme (black-on-green is weaker than it looks).
- Footer already includes `· <a href="privacy/">私隱政策</a>` (`:456` on 28 Nov `main`). Keep it.
- Ads may stay, but must not cover the filter row or the first result.

### Suggested implementation order (web)

1. Bug 1 and bug 2 (strings) — small, user-visible, no visual risk
2. Stale / error / loading states
3. Mobile cards + sticky desktop columns
4. A11y, 更多, wordmark, motion, favicon
5. Recheck at 1440, 768, and 390, light and dark, and with `prefers-reduced-motion`

## PlayFinder (`playfinder` branch, `app/`)

Source of record for this proposal: `HomeScreen.kt`, `SettingsScreen.kt`, `Theme.kt`, `MainActivity.kt`. The APK was not installed or screenshot for this proposal; verify visually on a device or emulator after the changes.

1. **Theme** — `Theme.kt` uses static teal `#00696E` / `#4FD8D8` and `dynamicColor: Boolean = true`. Map the static scheme onto `tokens.css` green (`#0e8a3e` / `#3fb950`). Default `dynamicColor` to **false**. Add a Settings toggle「跟隨系統顏色」for people who want dynamic colour.
2. **Stale banner** — `SyncBanner` in `HomeScreen.kt` shows `更新於 ${relativeTime()}`. After 60 minutes `relativeTime` returns time-only (`HH:mm`) with no date. Use an absolute HKT datetime after the first hour, and the same 2-hour stale treatment as the website (amber, 重新整理). Keep the existing offline-with-cache banner copy in `msg_offline`, or align it with `無法更新，以下係上次成功嘅資料`.
3. **黃金時段** — replace the simplified `黄金時段` string in `SlotRow` with `黃金時段`. If the badge plus a long venue name crowds the availability pill, keep the pill visible (ellipsis the venue first; wrap or drop the badge to the supporting line if needed).
4. **Settings** — the 私隱 card currently says「完整私隱政策見專案內 PRIVACY.md。」 Change that to a button or text link「閱讀私隱政策」that opens `https://hkteddychan.github.io/smartplay-live/privacy/`. Do not rewrite the policy text itself.
5. **Motion** — honour Android reduced-motion: no tab or sheet enter animation; pull-to-refresh may fade.
6. **Navigation** — `MainActivity.kt` already labels 場地 / 活動 / 通知 / 設定. Keep visible labels; do not switch to icon-only.
7. Do not change AdMob IDs, `applicationId`, or signing.

### Suggested implementation order (app)

1. Typo, privacy link, stale timestamp (copy and behaviour)
2. Token alignment and dynamic-colour default
3. SlotRow crowding / reduced motion
4. Visual QA on a phone-sized emulator, light and dark, including stale and offline-with-cache

## Acceptance

The update is not finished until:

- The two broken website strings are gone
- 390-wide facility results show venue, time, and remaining places together
- Stale and failed-refresh states exist on both web and app
- Web has skip link, `<body>`, `<main>`, labelled controls, 44px targets, Escape on the district popover, and reduced-motion
- Footer and Settings both reach the live privacy URL
- Ad IDs, application id, and keystore are unchanged
- A follow-up design review inspects a **rendered** result (web in a real browser at 1440 / 768 / 390; app on a device or emulator). This proposal’s app frames are mockups, not that review.

## Mockups in this folder

- `web/facility.html` — website, with a prototype state switcher
- `apk/app.html` — PlayFinder frames for 場地, 活動, 通知, 設定
- `tokens.css` — shared tokens

Prototype chrome (the state switcher) is not part of the product.
