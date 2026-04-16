# Noisy

**Noisy** is an async Python crawler that generates random HTTP/DNS traffic to mask your real browsing habits. It crawls the top 10,000 websites with realistic browser behaviour: randomised delays, diurnal activity patterns, per-domain rate limiting, and rotating user agents.

Comes with a **real-time web dashboard** for monitoring all metrics live.

---

## Quick Start

### Windows

Double-click **`start.bat`** — it creates a virtual environment, installs dependencies, and launches with the dashboard.

### macOS

Double-click **`start.command`** — same as above.

### Manual

```bash
git clone https://github.com/amartidandqdq/noisy.git
cd noisy
pip install -r requirements.txt
python noisy.py --dashboard
```

Open **http://localhost:8080** to view the dashboard.

---

## Dashboard

Launch with `--dashboard` to get a real-time web interface:

```bash
python noisy.py --dashboard
```

### Features

| Category | Feature |
|----------|---------|
| **Metrics** | Visited, failed, RPS, queued, unique URLs, active domains, bandwidth |
| **Error breakdown** | 4xx (client) / 5xx (server) / network errors per user |
| **Live log** | Scrolling feed of recent requests with status codes |
| **Top domains** | Ranked by traffic with health score bars |
| **TLD distribution** | Geo-diversity chart (.com, .fr, .jp, etc.) |
| **Diurnal curve** | 24h activity model with current position marker |
| **Stealth score** | Traffic fingerprint analysis (domain diversity, timing variance) |
| **Controls** | Pause/resume crawling, dark/light theme toggle |
| **Config editor** | Change sleep, depth, domain delay live without restart |
| **Export** | Download full metrics snapshot as JSON |
| **Alerts** | Banner when failure rate exceeds threshold |
| **Prometheus** | `/metrics` endpoint for Grafana integration |
| **Webhooks** | POST notifications on pause/resume/alert events |

---

## CLI Options

```bash
python noisy.py [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--dashboard` | off | Enable real-time web dashboard |
| `--dashboard-port` | 8080 | Dashboard port |
| `--dashboard-host` | 127.0.0.1 | Dashboard bind address |
| `--num_users` | 5 | Virtual users (parallel crawlers) |
| `--threads` | 10 | Concurrent fetches per user |
| `--max_depth` | 5 | Max link depth per crawl |
| `--min_sleep` | 2 | Min delay between requests (s) |
| `--max_sleep` | 15 | Max delay between requests (s) |
| `--domain_delay` | 5.0 | Min delay per domain (s) |
| `--crux_count` | 10000 | Number of top sites to crawl |
| `--dns_workers` | 3 | DNS noise workers |
| `--post-noise-workers` | 1 | HTTP HEAD noise workers |
| `--timeout` | none | Stop after N seconds |
| `--webhook-url` | none | Webhook URL for alerts |
| `--config` | none | JSON config file (CLI overrides) |
| `--dry-run` | off | Show config without crawling |
| `--validate-config` | off | Validate config and exit |

---

## Architecture

```
noisy.py                  Entry point + orchestration (130 lines)
noisy_lib/
  config.py               All constants (65 lines)
  config_loader.py        CLI parser + validation + JSON loader (105 lines)
  structures.py           LRUSet / BoundedDict / TTLDict (90 lines)
  profiles.py             UserProfile / UAPool / diurnal model (120 lines)
  extractor.py            HTML link extraction + blacklist (45 lines)
  fetchers.py             Fetch CRUX sites + user agents (100 lines)
  rate_limiter.py         Per-domain rate limiting (55 lines)
  fetch_client.py         HTTP GET with exponential retry (75 lines)
  crawler.py              UserCrawler + SharedMetrics (310 lines)
  workers.py              DNS noise / stats / UA refresh / HEAD noise (125 lines)
  dashboard.py            FastAPI + WebSocket dashboard server (280 lines)
  static/dashboard.html   Single-file dashboard UI (500 lines)
```

Each file has a 3-line header: purpose, inputs/outputs, and call graph.

---

## How It Works

1. Fetches the **CrUX top 10,000 sites** and primes each user's queue
2. Fetches **real user agents** from useragents.me (refreshed weekly)
3. Spawns N virtual users, each crawling independently with:
   - Randomised delays scaled by a **diurnal activity model** (less traffic at night)
   - **Per-domain rate limiting** shared across all users
   - **Domain health scoring** — auto-deprioritizes domains with high failure rates
   - URL **blacklist** applied before fetch and after link extraction
   - Exponential **retry on 5xx/network errors** (not on 4xx)
4. Background workers generate **DNS resolution noise** and **HTTP HEAD noise**
5. Stats reported every 60s to console; dashboard pushes via WebSocket every 2s

---

## Docker

```bash
docker build -t noisy .
docker run -it noisy --dashboard --dashboard-host 0.0.0.0
```

Docker Compose:

```yaml
services:
  noisy:
    build: .
    ports:
      - "8080:8080"
    command: --dashboard --dashboard-host 0.0.0.0
    restart: always
```

---

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -v    # 67 tests, <1s
```

---

## Authors

- [**Itay Hury**](https://github.com/1tayH) — *Initial work*
- [**madereddy**](https://github.com/madereddy) — *Docker build + Python upgrade*
- [**B3CKDOOR**](https://github.com/B3CKDOOR) — *Bugfixes*
- [**amartidandqdq**](https://github.com/amartidandqdq) — *Modular refactoring, dashboard, security audit*

## License

This project is licensed under the GNU GPLv3 License — see the [LICENSE](LICENSE) file for details.

## Acknowledgments

Inspired by [1tayH/noisy](https://github.com/1tayH/noisy). Forked from [madereddy/noisy](https://github.com/madereddy/noisy).
