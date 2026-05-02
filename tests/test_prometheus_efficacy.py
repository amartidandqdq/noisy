# Tests pour l'exposition des compteurs efficacy via /metrics (Prometheus format)

from noisy_lib import efficacy
from noisy_lib.dashboard_collector import MetricsCollector


class _FakeProfile:
    def __init__(self, uid):
        self.user_id = uid


class _FakeCrawler:
    def __init__(self, uid):
        self.profile = _FakeProfile(uid)
        self.stats = {
            "visited": 1, "failed": 0, "client_errors": 0,
            "server_errors": 0, "network_errors": 0, "bytes": 0,
        }


class _FakeRL:
    def active_domains_count(self):
        return 0


class _FakeCol:
    crawlers = [_FakeCrawler("u1")]
    shared_visited = set()
    rate_limiter = _FakeRL()


def test_prometheus_efficacy_counter_format():
    efficacy.reset()
    efficacy.bump("cookie_consent", 5)
    efficacy.bump("quic_probe", 2)
    out = MetricsCollector.prometheus_metrics(_FakeCol())
    assert "# TYPE noisy_efficacy_events_total counter" in out
    assert 'noisy_efficacy_events_total{feature="cookie_consent"} 5' in out
    assert 'noisy_efficacy_events_total{feature="quic_probe"} 2' in out


def test_prometheus_dns_prefetch_hit_rate():
    efficacy.reset()
    efficacy.bump_prefetch(True)
    efficacy.bump_prefetch(True)
    efficacy.bump_prefetch(False)  # hit_rate = 2/3 = 0.67
    out = MetricsCollector.prometheus_metrics(_FakeCol())
    assert "# TYPE noisy_dns_prefetch_hit_rate gauge" in out
    assert "noisy_dns_prefetch_hit_rate 0.67" in out


def test_prometheus_no_efficacy_section_when_empty():
    efficacy.reset()
    out = MetricsCollector.prometheus_metrics(_FakeCol())
    assert "noisy_efficacy_events_total" not in out
    # Non-efficacy metrics still present
    assert "noisy_requests_total" in out


def test_prometheus_label_sanitization():
    efficacy.reset()
    # Inject a hostile feature key (shouldn't happen in practice, but defensive check)
    efficacy.bump('evil"feature', 1)
    out = MetricsCollector.prometheus_metrics(_FakeCol())
    # Quote stripped -> label still parseable
    assert 'noisy_efficacy_events_total{feature="evilfeature"} 1' in out
