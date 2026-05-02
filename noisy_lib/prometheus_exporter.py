# prometheus_exporter.py - Format Prometheus text-based exposition
# IN: collector (crawlers, shared_visited, rate_limiter) + efficacy snapshot | OUT: text/plain
# APPELE PAR: dashboard_collector.MetricsCollector.prometheus_metrics | APPELLE: efficacy

from . import efficacy as _eff


def _sanitize_label(value: str) -> str:
    """Strip Prometheus-unsafe chars from label values (quote, backslash, newline)."""
    return value.replace('"', '').replace('\\', '').replace('\n', '')


def render(collector) -> str:
    """Build Prometheus text-format output from collector state + efficacy snapshot."""
    lines = []
    total_v = sum(c.stats["visited"] for c in collector.crawlers)
    total_4xx = sum(c.stats["client_errors"] for c in collector.crawlers)
    total_5xx = sum(c.stats["server_errors"] for c in collector.crawlers)
    total_net = sum(c.stats["network_errors"] for c in collector.crawlers)
    total_bytes = sum(c.stats["bytes"] for c in collector.crawlers)

    lines.append("# HELP noisy_requests_total Total HTTP requests")
    lines.append("# TYPE noisy_requests_total counter")
    lines.append(f'noisy_requests_total{{status="ok"}} {total_v}')
    lines.append(f'noisy_requests_total{{status="client_error"}} {total_4xx}')
    lines.append(f'noisy_requests_total{{status="server_error"}} {total_5xx}')
    lines.append(f'noisy_requests_total{{status="network_error"}} {total_net}')
    lines.append("# HELP noisy_bytes_total Total bytes received")
    lines.append("# TYPE noisy_bytes_total counter")
    lines.append(f"noisy_bytes_total {total_bytes}")
    lines.append("# HELP noisy_unique_urls Unique URLs visited")
    lines.append("# TYPE noisy_unique_urls gauge")
    lines.append(f"noisy_unique_urls {len(collector.shared_visited)}")
    lines.append("# HELP noisy_active_domains Active domains in rate limiter")
    lines.append("# TYPE noisy_active_domains gauge")
    lines.append(f"noisy_active_domains {collector.rate_limiter.active_domains_count()}")

    for c in collector.crawlers:
        uid = c.profile.user_id
        lines.append(f'noisy_user_visited{{user="{uid}"}} {c.stats["visited"]}')
        lines.append(f'noisy_user_failed{{user="{uid}"}} {c.stats["failed"]}')

    # Efficacy counters per stealth feature (events since process start)
    eff = _eff.snapshot()
    if eff:
        lines.append("# HELP noisy_efficacy_events_total Stealth feature events")
        lines.append("# TYPE noisy_efficacy_events_total counter")
        for feat, rec in eff.items():
            safe = _sanitize_label(feat)
            lines.append(f'noisy_efficacy_events_total{{feature="{safe}"}} {rec.get("count", 0)}')
        pf = eff.get("dns_prefetch", {})
        if "hit_rate" in pf:
            lines.append("# HELP noisy_dns_prefetch_hit_rate DNS prefetch hit rate (0-1)")
            lines.append("# TYPE noisy_dns_prefetch_hit_rate gauge")
            lines.append(f"noisy_dns_prefetch_hit_rate {pf['hit_rate']}")

    return "\n".join(lines) + "\n"
