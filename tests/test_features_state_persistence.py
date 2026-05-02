# Test: _get_all_features_state doit inclure tous les toggles applicables.
# Regression cible: cookie_consent + quic_probe ont ete oublies de la tuple,
# ce qui les empechait de persister apres restart.

from noisy_lib.dashboard_collector import MetricsCollector


class _FakeProfile:
    user_id = 0
    schedule = (8, 23)
    geo = "europe_fr"
    is_mobile = False
    diurnal_enabled = True


class _FakeCrawler:
    def __init__(self, features=None):
        self.profile = _FakeProfile()
        self.features = features or {}


def _state_for(features):
    """Helper: appelle _get_all_features_state avec features arbitraires."""
    col = MetricsCollector.__new__(MetricsCollector)
    col.crawlers = [_FakeCrawler(features)]
    col._search_workers = 0
    col.auto_pause_enabled = True
    return col._get_all_features_state()


# Tous les toggles que apply_features sait propager (whitelist dashboard_collector:614).
# Si un toggle est dans cette liste mais absent de _get_all_features_state, il
# sera applique au runtime mais perdu au restart.
APPLY_FEATURES_KEYS = (
    "tls_rotation", "realistic_depth", "referer_chains",
    "asset_fetching", "bandwidth_throttle", "dns_optimized",
    "dns_prefetch", "thirdparty_burst", "background_noise",
    "nxdomain_probes", "ech", "stream_noise",
    "cookie_consent", "quic_probe",
)


def test_all_apply_features_keys_are_persisted():
    """Chaque key acceptee par apply_features doit etre dans le state persiste."""
    state = _state_for({k: True for k in APPLY_FEATURES_KEYS})
    for key in APPLY_FEATURES_KEYS:
        assert key in state, f"Toggle '{key}' non persiste -> perdu au restart"
        assert state[key] is True, f"Toggle '{key}' devait etre True"


def test_cookie_consent_persisted():
    state = _state_for({"cookie_consent": True})
    assert state.get("cookie_consent") is True


def test_quic_probe_persisted():
    state = _state_for({"quic_probe": True})
    assert state.get("quic_probe") is True


def test_unset_features_default_false():
    state = _state_for({})
    for key in APPLY_FEATURES_KEYS:
        assert state[key] is False


def test_state_includes_non_feature_settings():
    state = _state_for({})
    # Reglages globaux
    assert state["schedule"] == "8-23"
    assert state["geo"] == "europe_fr"
    assert state["auto_pause"] is True
    assert state["diurnal"] is True
