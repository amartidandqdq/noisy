# Tests pour page_consent: detection CMP + simulate_consent (mock aiohttp)

import asyncio
import random

import pytest

from noisy_lib import efficacy
from noisy_lib.page_consent import CMP_MARKERS, detect_cmp, simulate_consent


def test_detect_cmp_finds_each_marker():
    for marker in CMP_MARKERS:
        html = f'<script src="https://cdn.{marker}/script.js"></script>'
        urls = detect_cmp(html)
        assert len(urls) == 1
        assert urls[0] == CMP_MARKERS[marker]


def test_detect_cmp_no_marker():
    html = "<html><body>Hello world</body></html>"
    assert detect_cmp(html) == []


def test_detect_cmp_empty_or_oversized():
    assert detect_cmp("") == []
    assert detect_cmp(None) == []
    huge = "x" * 2_000_001
    assert detect_cmp(huge) == []


def test_detect_cmp_multiple_markers():
    html = (
        'cookielaw.org and cookiebot.com and didomi.io'
    )
    urls = detect_cmp(html)
    assert len(urls) == 3


class _FakeResp:
    def __init__(self, body=b"x" * 1024):
        self._body = body
        self.content = self

    async def read(self, n):
        return self._body[:n]

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _FakeSession:
    def __init__(self):
        self.requests = []

    def get(self, url, **kwargs):
        self.requests.append((url, kwargs))
        return _FakeResp()


def test_simulate_consent_no_cmp_returns_zero():
    efficacy.reset()
    sess = _FakeSession()
    rng = random.Random(0)
    total = asyncio.run(simulate_consent(
        sess, "<html>nothing</html>", "https://x.com", {}, rng,
    ))
    assert total == 0
    assert sess.requests == []


def test_simulate_consent_caps_at_two():
    efficacy.reset()
    html = " ".join(CMP_MARKERS.keys())  # 8 markers
    sess = _FakeSession()
    rng = random.Random(0)
    total = asyncio.run(simulate_consent(
        sess, html, "https://x.com", {"User-Agent": "u"}, rng,
    ))
    assert total > 0
    # Max 2 endpoints/page
    assert len(sess.requests) <= 2


def test_simulate_consent_sets_referer_and_sec_fetch():
    efficacy.reset()
    html = "cookielaw.org"
    sess = _FakeSession()
    rng = random.Random(0)
    asyncio.run(simulate_consent(
        sess, html, "https://example.com/page", {"User-Agent": "u"}, rng,
    ))
    assert sess.requests, "expected at least 1 request"
    _, kwargs = sess.requests[0]
    h = kwargs["headers"]
    assert h["Referer"] == "https://example.com/page"
    assert h["Sec-Fetch-Dest"] == "script"
    assert h["Sec-Fetch-Site"] == "cross-site"


def test_simulate_consent_bumps_efficacy():
    efficacy.reset()
    html = "cookielaw.org"
    sess = _FakeSession()
    rng = random.Random(0)
    asyncio.run(simulate_consent(
        sess, html, "https://x.com", {}, rng,
    ))
    snap = efficacy.snapshot()
    assert snap.get("cookie_consent_detected", {}).get("count", 0) >= 1
    assert snap.get("cookie_consent", {}).get("count", 0) >= 1
