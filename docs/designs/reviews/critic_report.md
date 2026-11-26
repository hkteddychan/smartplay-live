# Stage 7 — Critic Review

Target: `docs/designs/2026-11-26-playfinder-android.md` (lines 1-151)
Reviewers: fresh-context Goldfish — `agents/design_critic.md`,
`agents/structural.md`, `agents/style.md` — read-only.

## Design critic (`agents/design_critic.md`)

### C1 — Blocker — no "Risks & Limits" section
The Feature Specification Standard requires an explicit risk section. The
shipped code carries: device-side 15-minute polling against a government
endpoint with no retry on HTTP failure; Doze/App Standby deferral; silent
notification-permission denial while the ad-paid week is still consumed; AdMob
test IDs in a release build; upstream schema/endpoint change silently stopping
alerts; unbounded cache staleness; an empty `proguard-rules.pro` with R8 on;
and an un-`DEBUG`-gated logging interceptor in release.
**Recommendation:** add a Risks & Limits section with a mitigation per risk.

### C2 — Blocker — the data-flow diagram is false
The diagram shows feed-api and ntfy arrows into the app; the code has one
upstream path. The deviation is not cosmetic: it changes cost (N devices × 5
sports × 96 requests/day), latency (15 minutes versus the pipeline's ~2-minute
mirror) and Doze exposure.
**Recommendation:** rewrite the push section with the chosen transport and its
characteristics.

### C3 — Blocker — the banner-ad model is both wrong and policy-risky
Forcing a three-minute banner dwell tracked by an impression listener is the
invalid-traffic pattern Google policy prohibits; the impression callback fires
once and cannot measure duration. The publisher id never reaches the SDK.
**Recommendation:** rewarded video + timed unlock, real AdMob ids, and a
policy-safe engagement mechanic.

### C4 — Blocker — "Approaches Considered" never evaluates the architecture it
chose
Missing: push transport, data-source topology, cache strategy, monetisation
models beyond the chosen one. The rejections that exist are subjective.
**Recommendation:** add H3 subsections per alternative with a decision line.

### C5 — Major — no repository interface exists
**Recommendation:** introduce the interface the design claims, and route the
worker through it. *(Disposition: interface dropped as speculative; the worker
now goes through the repository — see the consolidated report.)*

### C6 — Major — the push filter config is missing two of four dimensions
No weekday, no time window, and `setVenues` was never called, so the venue
predicate was always true.
**Recommendation:** add the missing predicates and the five-venue cap, or
amend the spec. *(Implemented.)*

### C7 — Major — the entitlement is device-local and the offline cache has no
freshness contract
A second device or a reinstall loses the watchlist, the grant and the ad
credit. The poller never wrote to Room and `fetchedAt` was never surfaced.
*(Disposition: the poller now refreshes the cache; the spec states the
entitlement limits.)*

### C8 — Major — security is never discussed
The AdMob SDK collects advertising ID and IP, and the app requests fine
location, yet the Anti-goals omit both and there is no data-safety statement.
`proguard-rules.pro` was empty with minify and shrinking on, the logging
interceptor was unconditional, and a missing `keystore.properties` produced a
release build with a null store file.
*(Implemented: keep rules, DEBUG-gated logging, explicit release-signing
failure.)*

### C9 — Major — four spec features are absent or different
No sale7 or activity notifications; no search debounce; the heatmap is a
time-of-day density chart rather than per-slot colouring; the deep link opens
the generic homepage because SmartPLAY exposes no per-slot URL.
*(Implemented where the code can honestly deliver it: debounce, heatmap wording,
deep-link wording.)*

### C10 — Nit — unsourced device coverage claim, no `targetSdk`, notification
ids overwrite each other
*(Implemented: notification ids are per session.)*

## Structural reviewer (`agents/structural.md`)

### S1 — Blocker — "Risks & Mitigations" section absent (same as C1)
**Recommended change:** insert a `## Risks & Mitigations` table with Risk |
Impact | Likelihood | Mitigation | Fallback.

### S2 — Blocker — the Alternatives Rule is not satisfied
Only UI toolchains are compared; the architecture alternatives are absent, and
the rejections are rationale-free ("overkill for Android-only v1").
**Recommended change:** add subsections for UI framework, push transport, data
source, monetisation, each with a `**Decision:**` line.

### S3 — Major — no "Proposed Architecture" heading
**Recommended change:** add `## Proposed Architecture` with Component Layout,
Data Flow, Data Layer and Tech Stack subsections, and correct the diagram.

### S4 — Major — the problem statement is missing
**Recommended change:** rename "Intent & Why" to "## Problem Statement" and
state the user, the friction and the workaround.

### S5 — Major — three scope buckets, no definition of the third
Goals, "Non-goals (v1)" and "Anti-goals" overlap and contradict each other.
**Recommended change:** collapse into `## Goals & Non-Goals` with Goals,
Non-Goals (v1) and Out of Scope (v2); move the two real constraints into
Constraints.

### S6 — Major — the monetisation table mixes a trigger with a state
**Recommended change:** split into a `| Trigger | Reward |` table plus a
separate eligibility table, and state one mechanism.

### S7 — Major — orphaned lifecycle scaffolding
**Recommended change:** delete "Builder Check" and "Next Step"; convert "What's
Left to the Builder" into "Implementation Status".

### S8 — Major — alternatives are evaluated before the architecture they judge
**Recommended change:** order the document Problem → Goals → Architecture →
Alternatives → Risks.

### S9 — Major — Goals and Features do not reconcile
Goals promise a heatmap and venue starring; Features specify neither. Features
"Search" and "Settings" appear in no goal.
**Recommended change:** align the two lists.

### S10-S14 — Nits
Malformed diagram fences; duplicated publisher id; inconsistent H3 numbering;
"My Calls" is undefined vocabulary; the pickleball dependency is filed as a
non-goal rather than a risk; an emoji inside a plain-text bullet.

## Style reviewer (`agents/style.md`)

### Y1 — Blocker — three false claims in the monetisation section
"3-min AdSense banner", "AdView impression listener", "ntfy anonymous
subscription activated client-side" — none of these exist.
**Recommended rewrite:** "Watch one rewarded video to completion, then remain on
the Notifications screen for three minutes to unlock one week of push alerts.
The ad currently uses Google's public test unit id and must be replaced with the
production unit before release."

### Y2 — Blocker — the push features do not exist
**Recommended rewrite:** "Push is device-local: a WorkManager job polls the LCSD
feed every 15 minutes while a grant is active, and notifies only when a
session's availability increased since the previous snapshot."

### Y3 — Major — three documented availability colours, two implemented
**Recommended rewrite:** "Availability is shown as a count pill (green when
slots remain, red when full). The heatmap shades each two-hour window by how
many available sessions start in it, on a single-colour light-to-dark ramp."
*(Note: the live feed populates `Available_Courts` on every row, so a "no
data" state has no data source.)*

### Y4 — Major — "time range slider" and "debounced 300ms" are not what ships
**Recommended rewrite:** describe the preset chips and the debounce accurately.

### Y5 — Major — the ntfy, feed-api and repository-interface claims are absent
**Recommended rewrite:** "The app fetches the LCSD open-data API directly and
caches it in Room. There is no server component and no push broker; a feed-api
Worker can be added later behind the repository."

### Y6 — Major — the deep link implies per-slot URLs
**Recommended rewrite:** "The slot overflow menu opens the LCSD SmartPLAY home
page in the system browser; the app does not build per-slot booking URLs.
Programme activities open the registration URL supplied by the LCSD feed."

### Y7 — Major — stale builder instructions
**Recommended rewrite:** replace with a one-line status block.

### Y8 — Nit — chat residue and unprovable claims
`(user said "Approved" 2026-11-26)`, "Best Android UX", "Cleaner UX, higher
retention", "covers 95%+ devices", the SeekCourt claim.
**Recommended rewrite:** delete the approval quote and the unmeasurable claims.

### Y9-Y18 (plan and cross-document)
The plan claims ntfy, names files that were never created, claims 4 tabs that
are not the shipped 4 tabs, claims a CI workflow that did not exist, leaves 87
checkboxes unchecked, and states an APK size target that the debug build
misses. "Push" means three different things across the two documents; the
vocabulary mixes slot/session/venue/facility/location.
**Recommended rewrite:** mark the plan as executed, rewrite the file lists to
the as-built names, and use "session" for one bookable time block.
