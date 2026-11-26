# Changelog

All notable changes to SmartPLAY Live will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [5.0.0] - 2026-11-26

Plan 1 (P0–P3): the v4 n8n pipeline is replaced by a Python poller
(`feature/rebuild-v5`, 42 commits) that runs as a systemd service on the
Oracle VM, keeps SQLite as the single source of truth, and sends Telegram
alerts with ntfy as the fallback channel.

### 行為改變 (Behaviour changes)

- Polling cadence: one facility-sport round every 60s (120s in WAF safe
  mode); activity-prog every 900s in its own thread. Was: n8n cron every
  minute with a single combined fetch.
- Notifications: Telegram first; ntfy only as fallback (spec §5.4).
  Failed batches park in an `outbox` table and are retried once per cycle
  for up to 3 days.
- First start runs a **silent baseline** (`--seed` forces it): sessions are
  persisted, no events, no messages.
- Sequence numbers: until the Worker `/seq` route exists (Plan 2) the
  poller runs in **local-seq mode** (`SEQ_URL` empty): sequential numbers
  from `seq.json`, seeded from `MAX(events.seq)` at start; `seq_source`
  records the mode; no `resync` events are written.
- WAF handling: browser-like headers + a persistent cookie jar
  (`COOKIES_PATH`), the 90/150/240/300s backoff ladder is actually slept,
  and a payload below 50% of the previous row count (or the activity
  snapshot below half) is rejected instead of trusted.
- Escalation: 5 consecutive rounds with zero successful datasets — or 5
  raised failures, or any dead worker — exit non-zero so systemd restarts
  the unit; `OnFailure=smartplay-alert@%n` sends a Telegram alert.

### 需要手動步驟 (Manual steps)

- Oracle VM: `python3.10-venv` installed; deploy to `/opt/smartplay/`,
  create `.env` (TG_TOKEN, TG_CHAT, TG_THREAD, NTFY_URL; DB_PATH,
  COOKIES_PATH, SEQ_URL/SEQ_TOKEN optional — empty SEQ_URL selects
  local-seq mode), `systemctl enable --now smartplay-poller`.
- Start order matters: the first production round must be the baseline
  (`--seed` on first `--once`, or rely on auto-baseline from the empty DB).
- n8n 搬運工 v1/v2 remain **deactivated**; the API key is rotated at
  cutover (R55), together with the worker redeploy (Task 12).

### 回滾方法 (Rollback)

- `systemctl disable --now smartplay-poller` and remove `/opt/smartplay/`.
- Re-enable the n8n 搬運工 v2 workflow (`4dPLxXsAhSZaxCyf`) via the n8n
  API; the worker mirror and website resume unchanged (restore README in
  the `smartplay-ops-backup` repo, tag `pre-rebuild-2026-11-26`).
- The v4 website and legacy worker feed are untouched by this release.

[5.0.0]: https://github.com/hkteddychan/smartplay-live/releases/tag/v5.0.0
