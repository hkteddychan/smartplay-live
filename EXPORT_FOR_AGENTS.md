# SmartPLAY / PlayFinder — Export for New Agent Continuity

## 1. OBJECTIVE
Build the PlayFinder Android app (Kotlin + Jetpack Compose) on the SmartPLAY data pipeline,
then run a comprehensive audit + EGM (Elephant-Goldfish Model) goldfish review cycle,
fixing every defect found. Also maintain the SmartPLAY website.

### v1 scope
- 6 sports + programme activities; no extra HK gov datasets
- Anonymous account; watchlist local (DataStore); share via WhatsApp/Telegram
- Play Store compliance: privacy policy, data safety, AAB, content rating 12+, disclaimer, AdMob policy
- Security: ProGuard/R8, cert pinning, SQLCipher, anti-debug, NDK secrets, network security config
- Formal verification: Lean 4 invariants (TLA+ skipped — not a concurrent protocol)

## 2. GITHUB
- Repo: https://github.com/hkteddychan/smartplay-live.git
- Git user: hkteddychan <hkteddychan@github.com>
- Default branch: main
- Active branch: playfinder (HEAD = 03dadedd40c75304b40ef2f9fc2a592c0486902a)
- Other branches: feature/rebuild-v5, feature/browse-page, main
- Tags: v1.1, v1.2, v1.3, v1.3.1, v1.3.2, v1.4
- Auth: GitHub CLI (`gh auth git-credential`)

### Key paths
- Website: D:\Teddy\Opencode\SmartPLAY\repo
- Android app (worktree): D:\Teddy\Opencode\SmartPLAY\SmartPLAY-playfinder
- All work is on branch `playfinder` in the worktree.

## 3. BUILD ENVIRONMENT
- OS: Windows 11 (win32)
- JAVA_HOME: C:\Users\Teddy\.jdks\jbr-17.0.14
- Gradle 8.9: %TEMP%\gradle89\gradle-8.9\bin\gradle.bat
- Android SDK: C:\Users\Teddy\AppData\Local\Android\Sdk
- Shell: PowerShell (no `tail`, `grep` — use Select-Object / Select-String)
- Temp dir: C:\Users\Teddy\AppData\Local\Temp\opencode

### Build commands
```
$env:JAVA_HOME="C:\Users\Teddy\.jdks\jbr-17.0.14"
cd D:\Teddy\Opencode\SmartPLAY\SmartPLAY-playfinder
.\gradlew.bat test assembleDebug bundleRelease --no-daemon
```

## 4. SKILLS (available via OpenCode skill tool)
Invoke by id (bare name, no superpowers: prefix):

| id | purpose |
|---|---|
| brainstorming | Creative work before any feature/build |
| browser | In-app browser (open/read/click/fill/screenshot) |
| diagnosing-superpowers | Debug a superpowers session that went wrong |
| dispatching-parallel-agents | 2+ independent tasks in parallel |
| executing-plans | Execute an implementation plan inline |
| finishing-a-development-branch | Decide how to integrate completed work |
| opencode | OpenCode itself: config, plugins, SDK, MCP, etc. |
| receiving-code-review | Handle code review feedback rigorously |
| report | Report an opencode issue/bug to GitHub |
| requesting-code-review | Verify work before merge |
| subagent-driven-development | Execute plan with subagents |
| systematic-debugging | Debug any bug/test failure |
| test-driven-development | TDD workflow |
| using-git-worktrees | Isolated worktree setup |
| using-superpowers | How to find/use skills (already loaded) |
| verification-before-completion | Evidence before success claims |
| writing-plans | Multi-step implementation plans |
| writing-skills | Create/edit/verify skills |

### Skill priority
Process skills first (brainstorming, systematic-debugging), then implementation skills.

## 5. ARCHITECTURE DECISIONS
- Native Kotlin + Compose; repository pattern for backend swap
- Inline execution in worktree on branch `playfinder`
- Push is device-local: WorkManager polls LCSD API every 15 min; NO ntfy, no server broker
- Rewarded video + 180s in-app dwell gate buys one week of push
- Watchlist lives in DataStore (not Room); cache is Room
- Release detection compares snapshots (Room `release_events` table), not a seen-key set
- Package contracts under `app/src/main/java/com/playfinder/app/**/README.md` (Interface / Invariants / Side Effects)

## 6. KEY TECHNICAL FACTS
- WorkManager initialised manually in PlayFinderApp.onCreate (default initializer removed in manifest)
  - Because Hilt worker factory must be available before WorkManager runs
- Room DB: slots (cache), activities, release_events
- DAOs: SlotDao, ActivityDao, ReleaseEventDao
- Release events: id = session identity, REPLACE on conflict, newest-first, pruned after 24h
- Activity query: `startDate <= :to AND (endDate = '' OR endDate >= :from)` (running courses kept)
- SlotPollWorker: matches watchlist, max 20 notifications/poll, max 3 retry attempts, quiet hours
- AlertNotifier.notifyRelease returns Boolean (false = not posted, keep event)
- MobileAds initialised in PlayFinderApp.onCreate
- ProGuard/R8 rules present; release smoke test in CI

## 7. COMPLETED WORK
- Website fixes (HKT timestamp, AdSense, ads.txt, footer) pushed to main
- App scaffolded: Gradle wrapper, Hilt, Compose NavHost, LCSD Retrofit API, Room, repos, alerts, AdMob rewarded, watchlist DataStore, screens (Home, Activities, Alerts, Settings), deep link, privacy policy
- Critical runtime defects fixed (push expiry Int→Long, activities flow, duplicate slots, notification permission, MobileAds init, ProGuard, HTTP logging debug-only, signing guard, CI, ads.txt, debounce, activity registration period + date range, weekday/time-window/5-venue/quiet-hours filters, per-session notification ids, FilterEngine moved to core, release-detection via Room)
- UI/UX overhaul: filter sheet, loading/empty/error/offline states, pull-to-refresh, last-sync label, heatmap, availability pill, Material icons, dark theme, separate Alerts/Settings screens, long-press watchlist
- EGM review cycle: drift report, 8 stage reports, consolidated report, as-built spec rewrite, plan marked executed, per-package contracts
- Lean 4 invariants written; AUDIT.md; 23 unit tests; assembleDebug + bundleRelease succeed
- Code-correctness pass: WorkManager Hilt init, release-event starvation, lost alerts, activity range, retry cap, snackbar scope, CI release smoke test

## 8. REMAINING / NEXT STEPS
1. Replace test AdMob app/unit IDs with real ones (RewardedAdManager.kt has test IDs)
2. Replace and back up the upload keystore
3. Complete Play Console forms (privacy policy URL, data safety, content rating 12+, ads disclosure)
4. Add instrumented tests for Room schema/DAOs, poller, ad gate, deep link, ViewModels
5. Deferred with reasons: server-side push broker, sale7 digest, per-session starring, per-session booking deep links

## 9. KEY FILES
- PlayFinderApp.kt — Hilt worker factory wiring
- AndroidManifest.xml — default WorkManager initializer removed
- SlotPollWorker.kt — release event processing, retry cap
- PlayFinderRepository.kt — fetchAndCache, release event recording
- ReleaseEventDao.kt — pending() ordering and draining
- ActivityDao.kt — activity date range query
- AlertsScreen.kt — snackbar scope
- RewardedAdManager.kt — test AdMob unit ID placeholder
- docs/designs/2026-11-26-playfinder-android.md — as-built spec
- docs/AUDIT.md — verification evidence and defect log
- docs/designs/reviews/ — EGM review reports

## 10. NOTES FOR AGENTS
- Use OpenCode native `skill` tool with bare ids (no superpowers: prefix)
- Todo tracking: no todo tool in OpenCode v2; use markdown file or plan facility
- Subagents: `subagent` with `agent: "general"` or `"explore"`
- File edits: prefer `edit` for targeted changes, `write` for full overwrite, `shell` for deletion
- Worktree primary dir: SmartPLAY-playfinder on branch playfinder
- Website lives in main repo at D:\Teddy\Opencode\SmartPLAY\repo
