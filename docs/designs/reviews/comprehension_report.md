# Stage 6 — Comprehension Test

Target: `docs/designs/2026-11-26-playfinder-android.md` (lines 1-151)
Reviewer: fresh-context Goldfish (`agents/comprehension.md`), no code access.

## What this proposes

PlayFinder is a native Android app (Kotlin + Jetpack Compose, Android-only for
v1) for Hong Kong LCSD court vacancies and programme activities. It is
push-first: rather than searching repeatedly, the user watches slots/venues and
the app notifies them when a slot opens. Push access is gated by a
value-exchange loop — viewing a 3-minute AdMob/AdSense banner unlocks one week
of push alerts with user-chosen filters — and the data layer is designed so the
backing source can later be swapped from the direct LCSD API to a "feed-api
Worker" without UI changes.

## How the existing system works, per this document

LCSD open-data is pulled by an "Oracle poller" into SQLite, then splits two
ways: into a "feed-api Worker (Plan 2)" that the app would consume, and into
ntfy (hosted at ntfy.tedton.hk), which carries push alerts to the app over a
device-specific anonymous ntfy subscription. Until Plan 2 ships, the app
fetches the same endpoints directly and caches client-side. Locally the app
uses Room (SQLite) behind a repository interface with three sources
(`LcsdDataSource`, `FeedApiDataSource`, `RoomCache`); watchlist, filters and
the ad-unlock timer are all local and anonymous.

Both sections are paraphrasable. The gaps below are in definitions and in
links that do not connect.

## Findings

### 1. Blocker — "Oracle poller" is never defined
**Scope:** lines 9, 106.
A newcomer cannot tell what the poller is (a script, a Worker, a cron job on
some host), what "Oracle" refers to (Oracle Cloud? an Oracle DB?), where it
runs, whether it already exists in production, or who owns it. The whole
architecture depends on it: if it does not exist, the ntfy branch of the flow
does not exist either, and the push-first premise collapses. The ntfy-hosted
and feed-api components are equally undescribed but at least named after their
function; "Oracle poller" is opaque.

### 2. Blocker — "Plan 2" / "feed-api Worker" is never expanded
**Scope:** lines 32, 106, 110, 117, 121.
"Plan 2" is never expanded — whose plan, of what, and what ships in Plan 1. The
document treats Plan 2 as a real gate ("until Plan 2 ships feed-api…") while
simultaneously listing ntfy push as already available in Constraints, so a
reader cannot tell which of the two push paths is live in v1. "feed-api" itself
has no described API shape, endpoints, host or auth — only the URL
`ntfy.tedton.hk` is given for ntfy.

### 3. Blocker — "SmartPLAY v5 data pipeline" and the booking deep link are undefined
**Scope:** lines 5, 9, 100.
"SmartPLAY v5" is the stated foundation of the whole app but is defined
nowhere: no description of the platform, no meaning for "v5", no statement of
which parts of it the poller and feed-api belong to. Line 100's "open
SmartPLAY booking page in browser" gives no URL, package or URI scheme, so the
deep-link feature (Goal, Feature 6) is unimplementable from the text.

### 4. Blocker — the anonymous ntfy push mechanism is asserted, not described
**Scope:** lines 63, 89, 138.
The mechanism is asserted, not described. A newcomer needs to know how the
device creates or holds an anonymous topic, how the poller learns that topic so
it can post to it (the data flow has no device→server registration step), and
how an anonymous ntfy subscription can carry *push* at all — ntfy's anonymous
`topic` endpoint is read-only, and posting normally needs auth. Line 89
(subscribe under Watchlist & Push) and line 63 (subscription "activated
client-side" only after the ad view) also contradict each other about when the
subscription exists.

### 5. Blocker — the 3-minute ad gate is three separate gaps
**Scope:** lines 58, 62, 130.
(a) "banner must stay visible (overlay or scroll-lock)" is an unresolved
either/or, not a spec, and neither is standard AdMob behaviour; the document
never says which. (b) "AdView impression listener" does not report *view
duration* — the impression callback fires once on display, so the tracking
mechanism as described does not exist. (c) Line 130 says "banner + rewarded
video for the 3-min view" while the reward table says banner only — a newcomer
cannot tell whether the three-minute requirement applies to the banner, the
rewarded video, or both.

### 6. Major — AdSense and AdMob are mixed together
**Scope:** lines 18, 35, 65, 130.
AdSense and AdMob are different products with different identifiers and SDKs.
The document mixes them: which account, which SDK and which identifier serve
and verify the ad? The entitlement is also never placed — if it is purely
on-device state, clearing app data resets the timer, while "Push active until
2026-12-03" implies a server-side or signed record that is nowhere described.

### 7. Major — "sale7 digest" is undefined
**Scope:** line 90.
"sale7" is never defined and does not correspond to anything in the referenced
LCSD open-data index. A newcomer cannot tell whether it is an LCSD sales
session, an internal feed name or a typo, nor what a digest contains, nor
whether it is subject to the user's filters.

### 8. Major — "SeekCourt" appears without introduction
**Scope:** line 79.
Used as a benchmark without indicating whether it is an app, a website or a
competitor, and with no comparison criteria beyond one feature.

### 9. Major — "quiet hours" has no semantics, and district filtering appears in one place only
**Scope:** line 94.
Listed as a settings field with no semantics: whose timezone, what it silences
(slot alerts only, or also the digest), and whether it overrides the ad-unlock
window. The filter config lists "sport, weekday, time range, up to 5 venues"
while Settings lists "sports, districts" — the district filter appears in only
one of the two lists.

### 10. Major — the Goals promise a heatmap that Features never describes
**Scope:** line 12 versus lines 70-72.
The Goals promise a visual heatmap; Feature 1 describes sport chips → venue
cards → date picker → time-slot list with a colour legend. Nothing in Features
is a heatmap (which would imply a day × time grid). A newcomer would build the
wrong primary UI.

### 11. Major — the data flow draws no programme-activity path
**Scope:** lines 103-110 versus 75-79.
The flow shows only court data. Line 110's "same endpoints as poller" is the
only hint, with no endpoint names, schemas or freshness expectations for
either domain, so `LcsdDataSource` cannot be specified from this text. The
label "LCSD API, v1" also leaves an unexplained versioning scheme on a
third-party source.

### 12. Major — ntfy is described as a push mechanism it cannot provide
**Scope:** line 129.
A background SSE or polling connection is not a push mechanism on Android; the
document never says how an alert arrives when the app is killed (foreground
service, FCM bridge, battery-optimiser exemption). A newcomer would reasonably
assume ntfy behaves like FCM. Line 142 lists the mechanism as still open, so
the core "push-first" promise rests on an unresolved question.

### 13. Nit — dispatch instructions left inside an approved design
**Scope:** lines 147-148, 151, and the Status line.
Tool-dispatch instructions and a quotation of the approval conversation sit
inside the design document. "Builder Check: To be dispatched after design
approval" reads like a checklist to complete; it is a dispatch note.

### 14. Nit — Non-goals and Anti-goals are not distinguished, and LCSD is never expanded
**Scope:** lines 20-29, and every use of "LCSD".
Line 24 ("iOS (Android-only v1)") reads like a constraint rather than a
non-goal. "LCSD" is never expanded to Leisure and Cultural Services
Department.
