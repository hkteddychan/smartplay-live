# tests/conftest.py
"""Shared test fakes (R1)."""

import json


class FakeGateResponse:
    """Stand-in for the requests.Response a Gate returns."""

    def __init__(self, status_code: int, content_type: str, body: str) -> None:
        self.status_code = status_code
        self.headers = {"Content-Type": content_type}
        self.text = body

    def json(self):
        return json.loads(self.text)
