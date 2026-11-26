# Stage 5 — Initial Zoom Out Review

Target: `docs/designs/2026-11-26-playfinder-android.md` (lines 1-151)
Reviewers: fresh-context Goldfish (`agents/zoom_out.md`, `agents/inventive_catalyst.md`),
read-only, no conversation history.

## Finding 1 — Blocker — the push story is built on a component that does not exist
**Scope:** lines 32, 63, 89, 106-110, 129, 138, 142.
The design mandates ntfy (SSE to `ntfy.tedton.hk`, anonymous device topic) and
lists ntfy as a must-use source. No ntfy client exists in the app; what shipped
is `alerts/SlotPollWorker.kt`, a device-local WorkManager poll against the LCSD
API with a seen-key set in DataStore. The data-flow diagram has two arrows into
the app; the code has one. The client re-implements detection the server
poller already performs.
**Recommended change:** rewrite the push sections to declare the actual
architecture (device-local poll + local notification) and delete the ntfy
constraint and the SSE-vs-polling open question.

## Finding 2 — Blocker — the monetisation model contradicts itself and the code
**Scope:** lines 15, 58, 61-62, 88, 91, 130, 136 vs line 27 and line 136.
Line 62 mandates a banner that must stay visible for three minutes, tracked "via
AdView impression listener"; line 130 lists "banner + rewarded video"; line 27
and line 136 forbid always-on banners. The app has only a rewarded video plus
an in-app 180-second countdown — no `AdView`, no banner, no impression
listener. An impression callback fires once on display; it cannot measure
duration, and forcing a three-minute banner dwell is an invalid-traffic
pattern Google policy prohibits.
**Recommended change:** state one mechanism — rewarded video → 180 s in-app gate
→ one-week grant — and delete every banner mention.

## Finding 3 — Major — the "Repository (interface)" layer is speculative
**Scope:** lines 112-121.
`Repository (interface) → LcsdDataSource / FeedApiDataSource / RoomCache` does
not exist. The app has two concrete `@Singleton` repositories holding `LcsdApi`
and a DAO directly, and the "zero UI changes" swap claim is false as written.
`FeedApiDataSource` is a second implementation for a worker that does not exist.
**Recommended change:** describe the repositories as concrete classes and
delete the speculative data-source hierarchy.

## Finding 4 — Major — the watchlist is a filter set, not a starred slot
**Scope:** lines 15, 58, 88, 91, 144.
"Star slots/venues" and "long-press any slot" do not match the code, which
watches a sport + district (+ optional venue). The "up to 5 venues" cap was
unenforced, and "Room schema for cache + watchlist" became DataStore.
**Recommended change:** restate the watchlist as a filter set, drop the
per-slot star from v1, and say the watchlist lives in DataStore.

## Finding 5 — Major — "quiet hours", the sale7 digest and programme alerts are
not in the product
**Scope:** lines 90, 94.
**Recommended change:** move them to an explicit "not in v1" list (the push
preferences live on the Notifications tab, not in Settings).

## Finding 6 — Nit — the Flutter-migration rationale is an architectural
dead-end
**Scope:** lines 52, 135.
A Kotlin repository interface does not reduce the cost of a Flutter port.
**Recommended change:** justify the repository pattern by upstream
swappability only.

## Finding 7 — Nit — the 300 ms debounce is speculative latency
**Scope:** line 83.
The filter runs over an in-memory list.
**Recommended change:** delete "(debounced 300ms)" — or implement it; the
implementation now does debounce, so the spec keeps the wording.

## Finding 8 — Nit — the AdSense publisher id is the wrong credential type for
AdMob
**Scope:** lines 35, 65, 130.
**Recommended change:** name the AdMob app id and rewarded unit id and point at
the placeholders.

## Finding 9 — Nit — the deep link implies per-slot URLs that do not exist
**Scope:** lines 99-102.
**Recommended change:** state that slot taps open the generic SmartPLAY site
and only activity cards deep-link to their own registration URL.

## Finding 10 — Nit — stale process scaffolding
**Scope:** lines 140-151.
**Recommended change:** replace "What's Left to the Builder" / "Builder Check" /
"Next Step" with a status block.

## Inventive-catalyst findings (Stage 5, second reviewer)

### Finding A — Blocker — server-side push versus device-local filters
The design demands both a server pipeline that publishes to ntfy and filters
that never leave the device. These cannot coexist without a server-side filter
registry, so the resolution was to delete the server side: the device re-fetches
the raw feed every 15 minutes and re-derives the diff. Cost: N devices × full
snapshots (13,664 rows for badminton alone), a 15-minute WorkManager floor that
Doze stretches to hours, and a client-side re-implementation of change
detection.
**Resolution:** segment the event namespace — publish each event to topics keyed
by (sport, district[, venue]) and let the app subscribe only to matching
topics. **Secondary trade-off:** fan-out multiplies publishes, the topic
namespace must be versioned, and push acquires a server dependency.
*Disposition:* kept as a v2 option; v1 stays device-local and the spec now
states the trade-off instead of pretending otherwise.

### Finding B — Blocker — the entitlement is local while the value is not
The grant is a self-asserted DataStore flag and timestamp; editing
`push_enabled` buys a year of push. If push ever moves server-side, a
client-local gate cannot stop anyone subscribing to a public topic, so the
monetisation evaporates exactly when push becomes valuable.
**Resolution:** inversion with a pseudonymous device credential — the device
generates a random secret, the feed-api exchanges it for a short-lived signed
subscription after checking the grant expiry. **Secondary trade-off:** a
server-side registry, expiry and revocation logic; the privacy wording must
change; a Worker outage means no alerts.
*Disposition:* recorded as a v2 risk in the spec's Risks table.

### Finding C — Major — the three-minute reward measures the wrong thing
**Resolution:** extract the two jobs — reward trigger = standard rewarded video
on completion; if genuine three-minute exposure is required, implement it as a
visible time-boxed banner with a foreground-aware visible timer.
**Secondary trade-off:** two ad surfaces means more SDK and policy exposure, and
a busier reward state machine.
*Disposition:* v1 keeps the rewarded video plus the in-app dwell; the spec now
says exactly what the three minutes measure.

### Finding D — Major — the bounded key store breaks the "notify once" invariant
On the shipped feed badminton has 13,664 rows, 4,786 with availability above
zero. The first poll sees an empty seen-set, so every available session looks
fresh; the 800-key cap then re-announces the rest on the next poll. The diff is
also key-based, not value-based, so a session going 2 → 4 courts is never
announced.
**Resolution:** reuse the cached snapshot — alert only when availability
increased. Dedupe becomes exact and the DataStore blob disappears.
**Secondary trade-off:** a diff is only valid against a complete previous
snapshot, so snapshot writes need an atomic replace.
*Disposition:* **implemented.** Release detection moved into the repository
(`core/ReleaseDetector`), events are stored in a Room table, and the DataStore
seen-key set was deleted.

### Finding E — Nit — the worker bypasses the repository boundary
**Disposition:** **implemented.** The worker now goes through
`PlayFinderRepository`, so the poll also refreshes the offline cache.

## Verdict

A genuine contradiction existed: the design mandates ntfy/SSE push and a
banner-ad monetisation model that the app replaced with a local LCSD poller and
a rewarded video. The design no longer described the product it authorised.
