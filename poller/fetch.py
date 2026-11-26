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
# I3: 100 rows is ~0.3% of a real payload, so it cannot catch a truncated
# download. Reject anything below half of the previous successful row count.
MIN_PREVIOUS_RATIO = 0.5


@dataclass
class FetchResult:
    name: str
    ok: bool
    records: list[dict]
    bytes: int
    error: str | None


def fetch_dataset(
    gate, base_url: str, name: str, *, prev_count: int | None = None
) -> FetchResult:
    """Download one dataset and validate it; never trust a partial payload.

    ``prev_count`` is the previous successful payload's row count for this
    dataset (``dataset_status.records``). A payload below
    :data:`MIN_PREVIOUS_RATIO` of it is truncated or filtered, not a real
    shrink, and must keep the stored snapshot. No baseline (first success)
    skips the relative check.
    """
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
    if name != ACTIVITY:
        if len(records) < MIN_FACILITY_RECORDS:
            return FetchResult(name, False, [], 0, "suspiciously_small")
        if (
            prev_count is not None
            and prev_count > 0
            and len(records) < prev_count * MIN_PREVIOUS_RATIO
        ):
            return FetchResult(name, False, [], 0, "suspiciously_small")
    return FetchResult(name, True, records, len(resp.text.encode("utf-8")), None)
