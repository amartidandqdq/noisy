# Tests pour efficacy: bump counters, sliding window hit-rate, thread-safety

import threading

from noisy_lib import efficacy


def test_bump_increments_count():
    efficacy.reset()
    efficacy.bump("feat_a")
    efficacy.bump("feat_a", 3)
    snap = efficacy.snapshot()
    assert snap["feat_a"]["count"] == 4


def test_bump_records_last_ts():
    efficacy.reset()
    efficacy.bump("feat_a")
    snap = efficacy.snapshot()
    age = snap["feat_a"]["last_age_s"]
    assert age is not None and age >= 0


def test_snapshot_empty_when_reset():
    efficacy.reset()
    assert efficacy.snapshot() == {}


def test_prefetch_hit_rate_basic():
    efficacy.reset()
    efficacy.bump_prefetch(True)
    efficacy.bump_prefetch(True)
    efficacy.bump_prefetch(False)
    snap = efficacy.snapshot()
    assert snap["dns_prefetch"]["hits"] == 2
    assert snap["dns_prefetch"]["misses"] == 1
    assert snap["dns_prefetch"]["hit_rate"] == 0.67


def test_prefetch_window_bounded():
    """Sliding window doit etre bornee a PREFETCH_WINDOW_SIZE."""
    efficacy.reset()
    n = efficacy.PREFETCH_WINDOW_SIZE + 500
    for _ in range(n):
        efficacy.bump_prefetch(True)
    snap = efficacy.snapshot()
    # Cumulatifs voient tout, window plafonne
    assert snap["dns_prefetch"]["hits"] == n
    assert snap["dns_prefetch"]["window_size"] == efficacy.PREFETCH_WINDOW_SIZE


def test_prefetch_window_reflects_recent_only():
    """Apres un long passe favorable, la window doit refleter le present."""
    efficacy.reset()
    # Past: 1000 hits (rempli la window)
    for _ in range(efficacy.PREFETCH_WINDOW_SIZE):
        efficacy.bump_prefetch(True)
    assert efficacy.snapshot()["dns_prefetch"]["hit_rate"] == 1.0
    # Recent: 1000 misses -> window full of misses
    for _ in range(efficacy.PREFETCH_WINDOW_SIZE):
        efficacy.bump_prefetch(False)
    snap = efficacy.snapshot()
    # Cumulatifs gardent la memoire, window est sensible
    assert snap["dns_prefetch"]["hits"] == efficacy.PREFETCH_WINDOW_SIZE
    assert snap["dns_prefetch"]["misses"] == efficacy.PREFETCH_WINDOW_SIZE
    assert snap["dns_prefetch"]["hit_rate"] == 0.0


def test_thread_safety_concurrent_bumps():
    """N threads bumpent en concurrence -> count exact (pas de race)."""
    efficacy.reset()
    n_threads = 10
    bumps_per_thread = 1000

    def worker():
        for _ in range(bumps_per_thread):
            efficacy.bump("concurrent_feat")

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    snap = efficacy.snapshot()
    assert snap["concurrent_feat"]["count"] == n_threads * bumps_per_thread


def test_thread_safety_concurrent_prefetch():
    """N threads bumpent prefetch hit/miss -> totaux exacts."""
    efficacy.reset()
    n_threads = 8
    per_thread = 500

    def hit_worker():
        for _ in range(per_thread):
            efficacy.bump_prefetch(True)

    def miss_worker():
        for _ in range(per_thread):
            efficacy.bump_prefetch(False)

    threads = []
    for _ in range(n_threads // 2):
        threads.append(threading.Thread(target=hit_worker))
        threads.append(threading.Thread(target=miss_worker))
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    snap = efficacy.snapshot()
    expected = (n_threads // 2) * per_thread
    assert snap["dns_prefetch"]["hits"] == expected
    assert snap["dns_prefetch"]["misses"] == expected
