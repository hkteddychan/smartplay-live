"""Fetch LCSD datasets and decide whether the payload can be trusted.

The source sits behind an Alibaba anti-bot WAF that answers with HTML
error pages and 405s, and it has no conditional GET, so every cycle
downloads in full. A wrong "ok" here would be diffed against the last
good snapshot and recorded as thousands of fake slot-disappeared
events, so anything that is not a plausible full JSON list is rejected.

Gate.get records the status itself and raises GateBackoff on latch
statuses; that exception is deliberately left to propagate to the
cycle layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from poller.config import ACTIVITY

MIN_FACILITY_RECORDS = 100


@dataclass
class FetchResult:
    name: str
    ok: bool
    records: list[dict]
    bytes: int
    error: str | None


def fetch_dataset(gate, base_url: str, name: str) -> FetchResult:
    """Download one dataset and validate it; never trust a partial payload."""
    url = f"{base_url}/{name}/file"
    resp = gate.get(url)  # GateBackoff propagates; the cycle layer waits
    if resp.status_code != 200:
        return FetchResult(name, False, [], 0, f"http_{resp.status_code}")
    if "text/html" in resp.headers.get("Content-Type", ""):
        return FetchResult(name, False, [], 0, "html_response")
    try:
        records = resp.json()
    except ValueError:  # json.JSONDecodeError (also requests' variant)
        return FetchResult(name, False, [], 0, "bad_json")
    if not isinstance(records, list):
        return FetchResult(name, False, [], 0, "not_list")
    if len(records) == 0:
        return FetchResult(name, False, [], 0, "empty_payload")
    if name != ACTIVITY and len(records) < MIN_FACILITY_RECORDS:
        return FetchResult(name, False, [], 0, "suspiciously_small")
    return FetchResult(name, True, records, len(resp.text.encode("utf-8")), None)
