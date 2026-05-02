# CLAUDE.md — Guide maintenance IA pour Noisy

## Projet
Crawler async Python qui génère du trafic HTTP/DNS aléatoire pour masquer les habitudes de navigation.
Lance N utilisateurs virtuels qui crawlent les top 10 000 sites CRUX en parallèle.
Inclut un **dashboard temps réel** (FastAPI + WebSocket) pour monitorer toutes les métriques live.

## Lancer
```bash
python noisy.py --dashboard              # http://localhost:8080
python noisy.py --dry-run                # voir config sans crawler
python noisy.py --config config.json     # overrides JSON (legacy supporté)
```
Flags principaux : `--num_users N`, `--schedule 8-23`, `--geo europe_fr`, `--region europe`, `--tld fr,de`, `--mobile-ratio 0.4`, `--search-workers 2`, `--history-file urls.json`. Stealth toggles : `--prefetch-workers N`, `--dns-optimized`, `--thirdparty-burst`, `--background-noise`, `--nxdomain-probes`, `--ech`, `--stream-noise`. Tous configurables live via dashboard.

**Lancement non-dev** : double-clic `start.bat` (Win), `./start.sh` (macOS/Linux). Crée venv + installe deps + lance avec `--dashboard`.

## Tests
```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -v              # 83 tests, < 1s
```

## Règles de modularité (PROTECTED)

- **Max 180 lignes par fichier** (sauf `config.py` données pures, `dashboard_collector.py` god-object assumé)
- **1 fichier = 1 responsabilité** — si un fichier fait 2 choses, splitter
- **Données pures → `config.py`** (constantes, UAs, geo profiles, catégories, blocklists URLs)
- **Logique comportementale → fichier dédié** (profiles.py, crawler.py, etc.)
- **Utilitaires partagés → `__init__.py`** (`host_in_blocklist`, `extract_tld`)
- **Pas d'imports lazy** sauf pour éviter circular imports (dashboard ↔ crawler)
- **Pas d'accès `_private`** cross-fichier — utiliser properties/getters
- **`TYPE_CHECKING`** pour les type hints circulaires

## Architecture — 1 fichier = 1 responsabilité

```
noisy.py                  → Orchestration + entry point (300 lignes)
noisy_lib/
  __init__.py             → Utilitaires partagés: host_in_blocklist, extract_tld (19 lignes)
  config.py               → TOUTES constantes + données pures: geo, UAs, catégories (218 lignes)
  config_loader.py        → Parser CLI + validation + lecture JSON (144 lignes)
  structures.py           → LRUSet / BoundedDict / TTLDict (90 lignes)
  metrics.py              → SharedMetrics cross-crawler (127 lignes)
  profiles.py             → UserProfile / UAPool / stealth headers / diurnal + diurnal_sleep helper (231 lignes ⚠ over-180)
  extractor.py            → Extraction liens + assets HTML (84 lignes)
  fetchers.py             → Fetch CRUX / UAs / OISD+Hagezi blocklists / history (185 lignes)
  rate_limiter.py         → Délai inter-requêtes par domaine (54 lignes)
  fetch_client.py         → HTTP GET avec retry + throttle (80 lignes)
  crawler_session.py      → CrawlerBase: session, cookies, domaines (123 lignes)
  crawler.py              → UserCrawler: fetch + crawl_worker (150 lignes)
  workers.py              → DNS / stats / UA refresh / HEAD / search noise (220 lignes)
  tls_profiles.py         → Rotation cipher TLS + ALPN pour diversité JA3 (82 lignes)
  dns_resolver.py         → DNS TTL cache avec IP persistence via dnspython (111 lignes)
  dns_prefetch.py         → DNS prefetch browser-like depuis liens des pages (147 lignes)
  dns_stealth.py          → 3rd-party burst, background noise, micro-burst, NXDOMAIN (179 lignes)
  tcp_tls_probe.py        → TCP+TLS+GET Range (anti-DPI) partage par dns_prefetch + dns_stealth (55 lignes)
  ech_client.py           → ECH probe via curl_cffi + ech_worker periodique (88 lignes)
  stream_noise.py         → Simulation streaming CDN avec chunks (101 lignes)
  depth_model.py          → Modèle probabiliste profondeur crawl (28 lignes)
  referer_chain.py        → Simulation chaînes Referer réalistes (77 lignes)
  asset_fetcher.py        → Téléchargement partiel ressources statiques (86 lignes)
  cookie_store.py         → Persistance cookie jar JSON (59 lignes)
  throttle.py             → Token bucket bandwidth throttling (61 lignes)
  ws_noise.py             → WebSocket/SSE idle connections bruit (113 lignes)
  traffic_mirror.py       → Miroir cache DNS + bruit proportionnel (161 lignes)
  page_consent.py         → Detection CMP + simulation acceptation cookies (84 lignes)
  quic_probe.py           → QUIC Initial UDP/443 vers CDN HTTP/3-capables (108 lignes)
  blocklist_fuzzy.py      → Stem index pour catch variants hostname (84 lignes)
  efficacy.py             → Compteurs d'efficacite par feature stealth (60 lignes)
  dashboard_collector.py  → MetricsCollector + settings persistence + stealth worker lifecycle + Prometheus efficacy export (715 lignes)
  dashboard.py            → FastAPI routes + WebSocket + webhook + mount /css /js; lit index.html par requete (200 lignes)
  static/index.html       → Entry point + sidebar nav 5 onglets (Live/Users/Stealth/DNS/Domains)
  static/css/main.css     → Theme cyberpunk + responsive + dense mode + sidebar layout + feat-status dots
  static/js/app.js        → Router (tabs) + WS + REST + keyboard shortcuts (1-5, P, T, D)
  static/js/ui.js         → Render functions + esc() XSS helper + skeleton-once pour Stealth toggles
  static/dashboard.legacy.html → Ancien single-file (archive, non servi)
start.bat                 → Windows one-click launcher
start.command             → macOS double-clickable launcher (delegate vers start.sh)
start.sh                  → macOS/Linux one-click launcher (executable)
```

## Graphe de dépendances (DAG, pas de cycles)

```
config.py (feuille — 0 import noisy_lib)
  ← config_loader.py
  ← structures.py (0 import)
  ← tls_profiles.py ← config, ssl
  ← depth_model.py (0 import)
  ← referer_chain.py ← config
  ← throttle.py ← config
  ← cookie_store.py (0 import noisy_lib)
  ← metrics.py ← config
  ← profiles.py ← config, tls_profiles
  ← rate_limiter.py ← config, structures
  ← fetch_client.py ← config, tls_profiles, throttle
  ← extractor.py ← __init__
  ← asset_fetcher.py ← config
  ← fetchers.py ← config, profiles
  ← crawler_session.py ← config, cookie_store, metrics, profiles, throttle, rate_limiter, structures
  ← crawler.py ← crawler_session, depth_model, referer_chain, asset_fetcher, extractor, fetch_client, profiles
  ← dns_resolver.py ← config (dnspython)
  ← tcp_tls_probe.py ← config, tls_profiles
  ← dns_prefetch.py ← config, dns_resolver, tls_profiles, profiles, tcp_tls_probe
  ← dns_stealth.py ← config, dns_resolver, profiles, tcp_tls_probe
  ← ech_client.py ← config, tls_profiles (curl_cffi optional)
  ← stream_noise.py ← config, dns_resolver, tls_profiles, throttle
  ← workers.py ← __init__, config, fetchers, tls_profiles, dns_resolver
  ← ws_noise.py ← config, profiles
  ← traffic_mirror.py ← __init__, config, profiles, tls_profiles
  ← dashboard_collector.py ← config, profiles, workers
  ← dashboard.py ← config, dashboard_collector
  ← noisy.py (racine — importe tout)
```

## Règle de modification

| Je veux changer... | Lire/modifier uniquement |
|--------------------|--------------------------|
| Une constante (timeout, délai...) | `config.py` |
| Parser CLI ou validation | `config_loader.py` |
| Comportement HTTP (retry, headers) | `fetch_client.py` |
| Délai entre requêtes domaine | `rate_limiter.py` |
| Extraction de liens | `extractor.py` |
| Simulation utilisateur (sleep, AFK) | `crawler.py` |
| Modèle d'activité heure/jour | `profiles.py` (_diurnal_weight, diurnal_sleep, diurnal_scale) |
| Sources de sites/UA | `fetchers.py` |
| Stats ou bruit DNS/HEAD/search | `workers.py` |
| Dashboard routes / API | `dashboard.py` |
| Dashboard métriques / features | `dashboard_collector.py` |
| Dashboard layout / nav / styles | `static/css/main.css` |
| Dashboard tab routing / shortcuts | `static/js/app.js` |
| Dashboard render fonctions | `static/js/ui.js` |
| Dashboard structure HTML / onglets | `static/index.html` |
| Métriques agrégées cross-crawler | `metrics.py` (SharedMetrics) |
| Blocklists OISD (NSFW/phishing) | `fetchers.py` + `config.py` (OISD URLs) |
| Geo profiles / mobile UAs / fallback UAs | `config.py` (GEO_PROFILES, MOBILE_UA_POOL, UA_FALLBACK) |
| Stealth headers (Sec-Fetch, Sec-CH-UA) | `profiles.py` |
| TLD/région filter | `config.py` (REGION_PRESETS) + `noisy.py` |
| Features toggle (dashboard) | `dashboard_collector.py` (apply_features) |
| Settings persistence | `dashboard_collector.py` (.noisy_settings.json) |
| Utilitaire blocklist/TLD | `__init__.py` |
| TLS cipher rotation / JA3 | `tls_profiles.py` |
| Modèle profondeur crawl | `depth_model.py` |
| Chaînes Referer | `referer_chain.py` |
| Téléchargement assets statiques | `asset_fetcher.py` + `extractor.py` (extract_assets) |
| Persistance cookies | `cookie_store.py` |
| Bandwidth throttling | `throttle.py` |
| WebSocket/SSE bruit | `ws_noise.py` |
| Miroir trafic DNS | `traffic_mirror.py` |
| Session HTTP crawler (base) | `crawler_session.py` (CrawlerBase) |
| DNS TTL cache / IP persistence | `dns_resolver.py` (DnsCache) |
| DNS prefetch depuis page links | `dns_prefetch.py` |
| 3rd-party burst / background / micro-burst / NXDOMAIN | `dns_stealth.py` |
| ECH (Encrypted Client Hello) | `ech_client.py` |
| Streaming CDN simulation | `stream_noise.py` |
| Constantes DNS stealth / anti-DPI | `config.py` (THIRD_PARTY_DOMAINS, STREAMING_CDN_DOMAINS…) |
| Detection CMP cookies | `page_consent.py` (CMP_MARKERS) |
| QUIC/HTTP3 probe UDP | `quic_probe.py` (QUIC_CAPABLE_HOSTS, _build_quic_initial) |
| Stem fuzzy blocklist (numeric + label/TLD spray) | `blocklist_fuzzy.py` (MIN_STEM_LEN=8/MIN_VARIANTS=3 numeric ; MIN_LABEL_LEN=10/MIN_TLD_VARIANTS=3 spray) |
| Compteurs efficacy par feature | `efficacy.py` (bump, snapshot) |
| Container Docker | `Dockerfile`, `docker-compose.yml`, `.dockerignore` |

## Dashboard — fonctionnalités

Sidebar 5 onglets (raccourcis 1-5, P pause, T theme, D dense) :

| Onglet | Contenu |
|--------|---------|
| **Live** | Métriques (visited/failed/RPS/queued/bw), 4xx/5xx/net errors, stealth score, diurnal curve, fingerprint detail + **live request log (30) + recent errors (20)** |
| **Users** | Table virtual users + Quick Settings (schedule/geo/mobile/search) + Runtime Config + TLD/Region filter |
| **Stealth** | 14 feature toggles (Core/DNS/Anti-DPI) + **indicateur live/off/error** pour les 6 worker-backed, auto-save on click |
| **DNS** | Resolver système, blocklist count (OISD+Hagezi ~1.08M), DNS stealth status |
| **Domains** | Top 20 + health score, TLD distribution, 11 catégories couleurs |

Endpoints externes : `/metrics` (Prometheus), webhooks POST (pause/resume/alert), `/api/export` (snapshot JSON).

## Classes clés

| Classe | Fichier | Rôle |
|--------|---------|------|
| `SharedMetrics` | `metrics.py` | Métriques partagées : request_log, domain_stats, tld_counts, category_counts, timing_heatmap, fingerprint_score(), pause/resume |
| `RequestLogEntry` | `metrics.py` | namedtuple pour le log de requêtes |
| `FetchResult` | `fetch_client.py` | Résultat HTTP avec status, html, bytes_received, error_msg, is_client_error, is_server_error |
| `DnsCache` | `dns_resolver.py` | Cache DNS TTL-aware avec IP persistence (dnspython) |
| `MetricsCollector` | `dashboard_collector.py` | Agrège stats crawlers → JSON, feature control, settings persistence, TLD filter, user add/remove, **stealth worker lifecycle (_start/_stop + drain)** |
| `UserCrawler` | `crawler.py` | Crawl par utilisateur virtuel avec queue, semaphore, rate limiting |
| `UserProfile` | `profiles.py` | Profil utilisateur : UA, geo, mobile, schedule, stealth headers, fingerprint rotation |

## Pièges connus (PROTECTED)
- **ALPN h2 + aiohttp = crash** : `get_rotated_ssl_context()` est appelé par `profiles.py` (→ aiohttp) ET par raw sockets. Ne JAMAIS mettre h2 en default. Utiliser `include_h2=True` uniquement dans workers/dns_prefetch/dns_stealth/stream_noise.
- **`_save_settings({"features": data})` partiel** : `data` ne contient que la clé du dernier clic. Toujours sauvegarder via `_get_all_features_state()` pour l'état complet.
- **`venv/.deps_installed` marker** : Empêche `start.bat` de réinstaller. Supprimer manuellement si on ajoute de nouvelles dépendances à `requirements.txt`.
- **Socket leak TLS** : `await reader.read(...)` après `open_connection` peut throw, writer jamais fermé. Toujours `try/finally` avec `writer.close(); await writer.wait_closed()`. Sites concernés : `dns_prefetch.py`, `stream_noise.py`, `workers.py`.
- **Browser cache dashboard** : `/` doit renvoyer `Cache-Control: no-cache, must-revalidate` sinon browser sert la vieille HTML inline. Headers déjà set dans `dashboard.py`.
- **`is_mobile` flag != UA** : UA pool externe contient des UAs mobiles. Toujours dériver `is_mobile` de l'UA via `is_mobile_ua()` (`profiles.py`), pas du slot d'attribution.
- **`add_user()` doit hériter** : geo, schedule, diurnal du `crawlers[0].profile`. Sinon nouveaux users par défaut sans config dashboard.
- **`asyncio.get_event_loop()` deprecated** : Utiliser `get_running_loop()` dans toute coroutine. Removed in Python 3.14.
- **Default thread pool exhaustion** : DNS resolves bloquants doivent passer par `_DNS_EXECUTOR` dédié (64 threads, `dns_resolver.py`), pas le default executor (32 threads partagés).
- **Dashboard toggles worker-backed** : 6 features spawn workers (`dns_prefetch`, `thirdparty_burst`, `background_noise`, `nxdomain_probes`, `stream_noise`, `ech`). Si dashboard actif, `noisy.py` ne les spawn PAS au démarrage — c'est le collector qui gère via `setup_stealth_context()` + `sync_stealth_workers()`. Sans dashboard : fallback spawn direct via flags CLI.
- **Cancellation drain** : `_stop_stealth_worker` cancel + spawn `_drain_cancelled` task stocké dans `self._drain_tasks` (set avec `add_done_callback(discard)`). Évite `Task was destroyed but it is pending!` et GC de la drain task.
- **XSS dashboard** : `ui.js` a un helper `esc()` pour tous les data paths user-controlled (r.url/r.domain/dm.domain/e.url/e.error/u.ua/u.geo/t.tld/c.category). Tout nouveau render qui injecte des données du crawl doit passer par `esc()` ou utiliser `textContent`.
- **UI skeleton-once** : `renderStealthToggles` build le DOM une seule fois via `box.dataset.built`, puis ne fait que des state updates (toggle.classList, feat-status className/textContent). Évite les rebuilds innerHTML qui détruisent handlers et focus.
- **dashboard.py lit index.html à chaque requête** : pas de cache en mémoire. Changements HTML visibles après simple reload browser, pas de restart Python requis.
- **`apply_features` whitelist** : la boucle propage les flags vers `crawler.features` UNIQUEMENT pour les keys listées. Tout nouveau toggle (`cookie_consent`, `quic_probe`, …) doit etre ajoute sinon le clic UI reste inerte (toggle visuel ON mais state pas applique).
- **Sed-style edits sans assert** : modifs Python via `str.replace()` peuvent silencieusement no-op si le marqueur a derive d'un caractere. Toujours `assert old in src` avant `replace`. Bug vu cette session sur l'import `_efficacy_snapshot` perdu.
- **Docker CVE drift** : `python:3.12-slim` (Bookworm) trainait openssl/tar/pip vulnerables. Bump a `python:3.13-slim-trixie` + `apt upgrade -y` + `pip>=25.3` dans builder. Re-scan apres chaque rebuild.

## Invariants clés (PROTECTED)
- `DomainRateLimiter` est **partagé** entre tous les crawlers (cross-user rate limiting)
- `LRUSet shared_visited` est **partagé** — évite de visiter 2× la même URL
- `UAPool` est thread-safe (asyncio.Lock)
- Blacklist appliquée **avant** fetch ET **après** extraction (`extractor.py`)
- Retry uniquement sur erreurs 5xx et exceptions réseau (pas sur 4xx)
- 4xx **ne retire PAS** l'URL du shared_visited (évite thundering herd)
- 5xx/network **retire** l'URL du shared_visited (retry possible)
- Domain health : skip si < 20% success rate ET ≥ 10 samples
- Rate limiter locks bornés à 50K (éviction FIFO, pas de memory leak)
- Dashboard bind `127.0.0.1` par défaut (sécurité)
- HTTP noise = HEAD only (lecture seule, pas d'effets secondaires)
- `config.json` legacy supporté via `--config` (les flags CLI ont priorité)
- Blocklist = 2 niveaux : `domain_blocklist` (set, O(1), ~1.08M OISD NSFW + OISD Phishing + Hagezi Gambling + Hagezi Piracy) + `url_blacklist` (list, substring, ~30 patterns)
- `_host_in_blocklist()` vérifie hostname + tous domaines parents (a.b.com → b.com → com)
- Fingerprint rotation toutes les 15-60 min par user (Accept, Cache-Control, Sec-CH-UA, DNT)
- Cookie jar `unsafe=True` par crawler — simule persistance cookies cross-domain
- Settings auto-sauvegardées dans `.noisy_settings.json` à chaque changement dashboard

## Stealth features (groupées par couche)

Détails complets archivés dans `CLAUDE-Archive.md`. Référence rapide :

| Couche | Features | Fichiers |
|--------|----------|----------|
| **TLS / Fingerprint** | JA3 rotation (6 ciphers, 15-60min), stealth headers (Accept/Cache/Sec-CH-UA/DNT, 15+ combos), fingerprint rotation par session, ALPN h2+http1.1 (raw)/http1.1 (aiohttp) | `tls_profiles.py`, `profiles.py` |
| **HTTP behavior** | Realistic depth (50-70/20-30/remainder), referer chains (40/30/20/10), asset fetching (2-5/page Range), cookie persist, bandwidth throttle (fiber/4G/ADSL/3G) | `depth_model.py`, `referer_chain.py`, `asset_fetcher.py`, `cookie_store.py`, `throttle.py` |
| **Bruit fond** | WebSocket idle (2-5 conn), traffic mirror (DNS cache obs), HTTP noise HEAD-only, search noise (Google/Bing/DDG suit 1-3 résultats) | `ws_noise.py`, `traffic_mirror.py`, `workers.py` |
| **DNS stealth** | TTL cache (dnspython, respect TTL), DNS→TCP→TLS correlation, IP persistence, DNS prefetch (extraction page links), mode léger dns-optimized | `dns_resolver.py`, `dns_prefetch.py`, `workers.py` |
| **DNS advanced** | 3rd-party burst (8-25 CDN/tracker/page = effet iceberg), background noise (NTP/Spotify/Steam), micro-burst (30-60 sim. + silence), NXDOMAIN probes (Chrome intranet + captive) | `dns_stealth.py` |
| **Anti-DPI** | Range payload 4-12KB (vs HEAD 0-byte), ECH curl_cffi/BoringSSL, streaming noise (long CDN keep-alive chunks 128-512KB), QUIC Initial UDP/443 vers CDN HTTP/3 (Cloudflare/Google/Fastly/Akamai) | `dns_prefetch.py`, `ech_client.py`, `stream_noise.py`, `quic_probe.py` |
| **CMP** | Detection 8 markers CMP (OneTrust/Cookiebot/Didomi/Sourcepoint/Quantcast/TrustArc/Iubenda/Termly), fire 1-2 endpoints consent par page avec jitter | `page_consent.py` |
| **Defense** | Stem index (numeric variants `grandpashabet7092.com`) + label/TLD-spray index (variants type `themoviesflix.{com,net,cc,llc}` quand label ≥10 chars sur ≥3 TLDs distincts) | `blocklist_fuzzy.py` |
| **Observability** | Compteurs efficacy par feature (events count + hit-rate prefetch + last-activity), badge cyan sous toggles + export Prometheus (`noisy_efficacy_events_total{feature="..."}` + `noisy_dns_prefetch_hit_rate`) | `efficacy.py`, `dashboard_collector.py` |
| **Modèle activité** | Diurnal 24h (pic midi/creux nuit), scheduler (`--schedule 8-23` wrap), geo profiles (21 locales), mobile sim (10 UAs, Sec-CH-UA-Mobile), traffic replay JSON | `profiles.py`, `config.py` |
| **Filtrage / sécurité** | OISD NSFW 524K + Phishing 335K + Hagezi Gambling 214K + Hagezi Piracy 12K = ~1.08M, TLD/Region filter (6 presets), URL blacklist substring, auto-pause fail%>50, connection health check | `fetchers.py`, `extractor.py`, `dashboard_collector.py` |
| **UX dashboard** | Settings persistence (.noisy_settings.json), domain categories (11), live config edit, feature toggles + **status dots** (live/off/error), sidebar 5 tabs + raccourcis 1-5, `esc()` XSS helper | `dashboard_collector.py`, `static/` |

## Statut projet (récents)

Historique complet (P0→P4, 8+6+3+11 bugfixes, 9+5+4+5 features, ALPN/settings fixes, dashboard cleanup) → `CLAUDE-Archive.md`.

| Phase | État | Date |
|-------|------|------|
| Anti-DPI hardening (Range, ECH, stream, ALPN, IP persist) | ✅ | 2026-04 |
| Code review + 11 fixes + Dashboard refonte + bug fixes UX | ✅ | 2026-04-16 AM |
| Session XSS/Stealth-lifecycle : XSS esc(), ws re-raise, close() log, 6 worker toggles dynamiques + status dots, Logs→Live merge (6→5 tabs), Hagezi gambling/piracy (+227K), UI skeleton-once, cancellation drain | ✅ | 2026-04-16 PM |
| Cookie consent + QUIC/HTTP3 probe + efficacy badges + fuzzy stem blocklist + start.command + Docker (Trixie/CVE patches) + tooltip workers count | ✅ | 2026-04-18 |
| Fuzzy blocklist v2 (label/TLD spray) + efficacy → Prometheus export + Docker scan post-rebuild (0C/1H/3M/22L, tous "not fixed" upstream Trixie) | ✅ | 2026-05-02 |
| Tests | 94 verts, < 1s | 2026-05-02 |

- **Fork** : github.com/amartidandqdq/noisy (from madereddy/noisy)
- **⚠ dashboard_collector.py** : 715 lignes (god-object assumé, seule exception au max 180)

## Décisions clés

| Décision | Choix | Raison |
|----------|-------|--------|
| ALPN h2 | `include_h2=True` raw sockets only, http/1.1 default | aiohttp crash sur HTTP/2 framing |
| dnspython vs getaddrinfo | dnspython | getaddrinfo n'expose pas le TTL |
| curl_cffi pour ECH | BoringSSL via curl_cffi | Python ssl stdlib n'a aucun support ECH |
| IP persistence | Stocker N IPs, retourner toujours la 1ère pendant TTL | Browsers font pareil, évite churn détectable |
| Range payload anti-DPI | GET+Range 4-12KB au lieu de HEAD 0-byte | HEAD sans payload = pattern scan détectable |
| Dashboard split fichiers | static/index.html + css/main.css + js/{app,ui}.js | Single 919-line ingérable, vanilla split sans build |
| Sidebar nav 5 onglets | Live/Users/Stealth/DNS/Domains | Logs fusionnés dans Live (request log + errors), Quick Settings + Config dans Users |
| Worker-backed toggles dynamiques | Spawn/cancel via `apply_features` + drain task | Dashboard pilote le lifecycle, pas que l'état persistant |
| XSS escape helper | `esc()` dans ui.js sur data paths crawl-fed | r.url/r.domain/e.error viennent de sites adversariaux |
| UI skeleton-once | `box.dataset.built` flag, state updates seulement | Rebuild innerHTML détruit handlers + focus |
| Cancellation drain | `_drain_tasks` set + `add_done_callback(discard)` | Évite RuntimeWarning sans bloquer handler async |
| Hagezi Gambling/Piracy | URLs hardcodées config.py, `""` pour désactiver | Toggle 1-click pour filtrer 227K domaines supplémentaires |
| Dedicated DNS executor | `ThreadPoolExecutor(64)` | Microburst 30-60 resolves saturent default pool (32) |
| Cache-Control HTML | `no-cache, must-revalidate` sur `/` | Browser cache la vieille HTML sinon (StaticFiles a ETag pour CSS/JS) |
| `is_mobile` dérivé UA | `is_mobile_ua(ua)` substring match, pas du slot | UA pool externe contient mobiles, slot ment |
| `add_user()` hérite état | Copie geo/schedule/diurnal de `crawlers[0].profile` | Sinon ignore config dashboard |
| Depth model fourchettes | `bounce uniform(0.5,0.7)` re-tiré par session | Probabilité fixe = pattern détectable |
