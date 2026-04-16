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
| **Domain categories** | 11 categories (news, social, tech, ecommerce, etc.) with colored bars |
| **Timing heatmap** | 7×24 grid (day × hour) showing request intensity |
| **Controls** | Pause/resume, dark/light theme, add/remove users dynamically |
| **Config editor** | Change sleep, depth, domain delay live without restart |
| **Feature toggles** | Schedule, geo, mobile, search, auto-pause, diurnal — click on/off |
| **TLD/Region filter** | Region checkboxes + custom TLD, applied live |
| **Blocklist info** | OISD NSFW (404K) + phishing (362K) domains blocked |
| **Export/Import** | Save/load config JSON + export metrics snapshot |
| **Settings persistence** | `.noisy_settings.json` auto-saved, restored on restart |
| **Alerts** | Banner when failure rate exceeds threshold |
| **Auto-pause** | Auto-pause if fail% > 50% after 50+ requests |
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
| `--search-workers` | 0 | Search engine noise workers |
| `--schedule` | none | Active hours (e.g. `8-23`) |
| `--geo` | none | Geo profile (e.g. `europe_fr`, `asia_jp`) |
| `--mobile-ratio` | 0.3 | Ratio of mobile users (0–1) |
| `--region` | none | TLD region preset (repeatable: `europe`, `asia`, etc.) |
| `--tld` | none | Custom TLD filter (e.g. `fr,de,uk`) |
| `--history-file` | none | Browser history file (JSON/TXT) to mix in |
| `--timeout` | none | Stop after N seconds |
| `--webhook-url` | none | Webhook URL for alerts |
| `--config` | none | JSON config file (CLI overrides) |
| `--dry-run` | off | Show config without crawling |
| `--validate-config` | off | Validate config and exit |
| `--cookie-persist` | off | Persist cookies between sessions |
| `--ws-workers` | 0 | WebSocket noise workers |
| `--mirror` | off | Traffic mirror mode (DNS cache observation) |
| `--prefetch-workers` | 0 | DNS prefetch workers (browser-like link prefetching) |
| `--dns-optimized` | off | Lightweight mode: Connection:close, 64KB max, no assets |
| `--thirdparty-burst` | off | Third-party DNS burst (CDN/trackers/ads per page) |
| `--background-noise` | off | Background app DNS noise (NTP, Spotify, Steam...) |
| `--nxdomain-probes` | off | Chrome NXDOMAIN probes + captive portal checks |
| `--ech` | off | Encrypted Client Hello via curl_cffi (hides SNI from ISP) |
| `--stream-noise` | off | Streaming simulation (long CDN connections with chunks) |

---

## Architecture

1 file = 1 responsibility. Max ~200 lines per file. No circular imports (DAG).

```
noisy.py                     Entry point + orchestration (300 lines)
noisy_lib/
  __init__.py                Shared utils: host_in_blocklist, extract_tld
  config.py                  ALL constants + data: geo, UAs, categories, regions (218 lines)
  config_loader.py           CLI parser + validation + JSON loader (144 lines)
  structures.py              LRUSet / BoundedDict / TTLDict (90 lines)
  metrics.py                 SharedMetrics cross-crawler (127 lines)
  profiles.py                UserProfile / UAPool / stealth headers / diurnal (202 lines)
  extractor.py               HTML link + asset extraction (84 lines)
  fetchers.py                Fetch CRUX / UAs / OISD blocklists / history (169 lines)
  rate_limiter.py            Per-domain rate limiting (54 lines)
  fetch_client.py            HTTP GET with retry + throttle (80 lines)
  crawler_session.py         CrawlerBase: session, cookies, domain helpers (123 lines)
  crawler.py                 UserCrawler: fetch + crawl_worker (150 lines)
  workers.py                 DNS / stats / UA refresh / HEAD / search noise (220 lines)
  tls_profiles.py            TLS cipher + ALPN rotation for JA3 diversity (82 lines)
  depth_model.py             Probabilistic crawl depth model (28 lines)
  referer_chain.py           Realistic HTTP referer chain simulation (77 lines)
  asset_fetcher.py           Static asset partial downloads (86 lines)
  cookie_store.py            Cookie jar JSON persistence (59 lines)
  throttle.py                Token bucket bandwidth throttling (61 lines)
  ws_noise.py                WebSocket/SSE idle connection noise (113 lines)
  traffic_mirror.py          DNS cache mirroring + proportional noise (161 lines)
  dns_resolver.py            DNS TTL cache with IP persistence (111 lines)
  dns_prefetch.py            Browser-like DNS prefetch from page links (170 lines)
  dns_stealth.py             3rd-party burst, background noise, micro-burst, NXDOMAIN (163 lines)
  ech_client.py              Encrypted Client Hello probe via curl_cffi (66 lines)
  stream_noise.py            Streaming CDN simulation with chunked downloads (101 lines)
  dashboard_collector.py     MetricsCollector + settings persistence (520 lines)
  dashboard.py               FastAPI routes + WebSocket + webhook (198 lines)
  static/dashboard.html      Single-file dashboard UI
```

Each file has a 3-line header: purpose, inputs/outputs, and call graph.

---

## How It Works

1. Fetches the **CrUX top 10,000 sites** and primes each user's queue
2. Fetches **real user agents** from useragents.me (refreshed weekly)
3. Downloads **OISD blocklists** (766K+ NSFW/phishing domains) and filters them out
4. Spawns N virtual users, each crawling independently with:
   - **TLS fingerprint rotation** (JA3 diversity) — 6 cipher suite orderings, rotated every 15–60 min
   - **Realistic click depth** — 60% bounce, 25% short (2-3 pages), 15% deep browse
   - **Referer chain simulation** — 40% search engine, 30% direct, 20% social, 10% cross-site
   - **Static asset fetching** — 2-5 images/CSS/JS per page with Range headers
   - **Bandwidth throttling** — token bucket (fiber/4G/ADSL) per user
   - **Cookie persistence** — cross-session cookie replay (`--cookie-persist`)
   - Randomised delays scaled by a **diurnal activity model** (less traffic at night)
   - **Per-domain rate limiting** shared across all users
   - **Domain health scoring** — auto-skip domains with < 20% success rate
   - URL **blacklist** applied before fetch and after link extraction
   - Exponential **retry on 5xx/network errors** (not on 4xx)
   - **Stealth headers**: Sec-Fetch, Sec-CH-UA, fingerprint + TLS rotation every 15–60 min
   - **Geo profiles** with locale-aware Accept-Language and timezone offsets
   - **Mobile simulation** with real mobile UAs and reduced crawl depth
5. Background workers generate **DNS noise**, **HTTP HEAD noise**, **search engine noise**, and **WebSocket noise**
6. Optional **traffic mirroring** (`--mirror`) observes system DNS cache and generates proportional noise
7. **DNS stealth layer** (opt-in flags):
   - **DNS TTL cache** — respects TTL from DNS responses, no re-query before expiry
   - **DNS→TCP→TLS→SNI correlation** — every DNS query followed by real TCP+TLS handshake with payload
   - **DNS prefetch** (`--prefetch-workers`) — extracts domains from page links, resolves in burst (like Chrome)
   - **Third-party burst** (`--thirdparty-burst`) — resolves 8-25 CDN/tracker/ad domains per page (iceberg effect)
   - **Background app noise** (`--background-noise`) — NTP, Spotify, WhatsApp, Discord, Steam, Windows Update...
   - **Micro-bursting** — 30-60 simultaneous DNS queries then silence (human browsing pattern)
   - **NXDOMAIN probes** (`--nxdomain-probes`) — Chrome intranet redirect detector + captive portal checks
8. **Anti-DPI hardening** (opt-in flags):
   - **Range payload** — GET with Range header (4-12KB real data) instead of empty HEAD (defeats DPI heuristics)
   - **ALPN negotiation** — h2 + http/1.1 in every TLS handshake (browser fingerprint)
   - **IP persistence** — same IP per domain for entire TTL (no round-robin churn)
   - **ECH** (`--ech`) — Encrypted Client Hello via curl_cffi/BoringSSL (hides SNI from ISP)
   - **Streaming noise** (`--stream-noise`) — long-lived CDN connections with chunked downloads (simulates video)
9. Stats reported every 60s to console; dashboard pushes via WebSocket every 2s
10. **Auto-pause** if failure rate spikes above 50%

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
