# CLAUDE.md — Guide maintenance IA pour Noisy

## Projet
Crawler async Python qui génère du trafic HTTP/DNS aléatoire pour masquer les habitudes de navigation.
Lance N utilisateurs virtuels qui crawlent les top 10 000 sites CRUX en parallèle.
Inclut un **dashboard temps réel** (FastAPI + WebSocket) pour monitorer toutes les métriques live.

## Lancer
```bash
python noisy.py                          # infini avec défauts
python noisy.py --dashboard              # avec dashboard web sur :8080
python noisy.py --dashboard --dashboard-port 9090
python noisy.py --dry-run                # voir config sans crawler
python noisy.py --validate-config        # valider config et quitter
python noisy.py --config config.json     # charger overrides JSON
python noisy.py --num_users 3 --timeout 60 --webhook-url http://...
python noisy.py --schedule 8-23          # actif 08h–23h seulement
python noisy.py --geo europe_fr          # profil géo français
python noisy.py --region europe          # filtre TLD européens
python noisy.py --tld fr,de,es           # TLD spécifiques
python noisy.py --mobile-ratio 0.4       # 40% users mobiles
python noisy.py --search-workers 2       # bruit recherche Google/Bing
python noisy.py --history-file urls.json # replay historique navigateur
python noisy.py --prefetch-workers 2    # DNS prefetch depuis liens des pages
python noisy.py --dns-optimized         # mode léger: Connection:close, 64KB max
python noisy.py --thirdparty-burst      # burst DNS tiers (CDN/trackers/ads)
python noisy.py --background-noise      # bruit apps background (NTP/Spotify/Steam)
python noisy.py --nxdomain-probes       # probes NXDOMAIN Chrome + captive portal
python noisy.py --ech                   # ECH via curl_cffi (masque SNI du FAI)
python noisy.py --stream-noise          # simulation streaming vidéo (chunks CDN)
```

### Lancement rapide (non-dev)
- **Windows** : double-clic `start.bat`
- **macOS** : double-clic `start.command`

Les deux créent un venv, installent les dépendances, et lancent avec `--dashboard`.

## Tests
```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -v              # 67 tests, < 1s
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
  profiles.py             → UserProfile / UAPool / stealth headers / diurnal (202 lignes)
  extractor.py            → Extraction liens + assets HTML (84 lignes)
  fetchers.py             → Fetch CRUX / UAs / OISD blocklists / history (169 lignes)
  rate_limiter.py         → Délai inter-requêtes par domaine (54 lignes)
  fetch_client.py         → HTTP GET avec retry + throttle (80 lignes)
  crawler_session.py      → CrawlerBase: session, cookies, domaines (123 lignes)
  crawler.py              → UserCrawler: fetch + crawl_worker (150 lignes)
  workers.py              → DNS / stats / UA refresh / HEAD / search noise (220 lignes)
  tls_profiles.py         → Rotation cipher TLS + ALPN pour diversité JA3 (82 lignes)
  dns_resolver.py         → DNS TTL cache avec IP persistence via dnspython (111 lignes)
  dns_prefetch.py         → DNS prefetch browser-like depuis liens des pages (170 lignes)
  dns_stealth.py          → 3rd-party burst, background noise, micro-burst, NXDOMAIN (163 lignes)
  ech_client.py           → Encrypted Client Hello probe via curl_cffi (66 lignes)
  stream_noise.py         → Simulation streaming CDN avec chunks (101 lignes)
  depth_model.py          → Modèle probabiliste profondeur crawl (28 lignes)
  referer_chain.py        → Simulation chaînes Referer réalistes (77 lignes)
  asset_fetcher.py        → Téléchargement partiel ressources statiques (86 lignes)
  cookie_store.py         → Persistance cookie jar JSON (59 lignes)
  throttle.py             → Token bucket bandwidth throttling (61 lignes)
  ws_noise.py             → WebSocket/SSE idle connections bruit (113 lignes)
  traffic_mirror.py       → Miroir cache DNS + bruit proportionnel (161 lignes)
  dashboard_collector.py  → MetricsCollector + settings persistence (501 lignes)
  dashboard.py            → FastAPI routes + WebSocket + webhook (198 lignes)
  static/dashboard.html   → Single-file dashboard UI
start.bat                 → Windows one-click launcher
start.command             → macOS one-click launcher
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
  ← dns_prefetch.py ← config, dns_resolver, tls_profiles, profiles
  ← dns_stealth.py ← config, dns_resolver, tls_profiles, profiles
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
| Modèle d'activité heure/jour | `profiles.py` (_diurnal_weight) |
| Sources de sites/UA | `fetchers.py` |
| Stats ou bruit DNS/HEAD/search | `workers.py` |
| Dashboard routes / API | `dashboard.py` |
| Dashboard métriques / features | `dashboard_collector.py` |
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

## Dashboard — fonctionnalités

| Catégorie | Détail |
|-----------|--------|
| Métriques | visited, failed, RPS, queued, unique URLs, active domains, bandwidth |
| Erreurs | 4xx / 5xx / network errors par user, recent errors panel |
| Live log | 50 dernières requêtes avec status codes + clear button |
| Top domains | Top 20 par trafic avec health score + clear button |
| TLD distribution | Chart geo-diversity (.com, .fr, .jp…) + clear button |
| Domain categories | 11 catégories (news, social, tech, ecommerce…) avec barres colorées |
| Timing heatmap | Grille 7×24 (jour × heure) intensité requêtes |
| Diurnal curve | Modèle 24h avec marqueur position courante |
| Stealth score | Fingerprint (domain diversity, TLD diversity, timing variance) |
| Contrôles | Pause/resume, dark/light theme, +/- users dynamiques |
| Config editor | min_sleep, max_sleep, depth, domain_delay live |
| Features toggle | Schedule, geo, mobile, search, auto-pause, diurnal — tags cliquables on/off |
| TLD/Region filter | Checkboxes régions + TLD custom, appliqué live |
| Blocklist info | Compteur NSFW + phishing domaines bloqués (OISD) |
| DNS info | Serveurs DNS système avec expandable list |
| Export/Import | Save/Load config JSON + export métriques snapshot |
| Settings persistence | .noisy_settings.json auto-saved, restauré au redémarrage |
| Alertes | Bannière si fail% > seuil |
| Auto-pause | Pause auto si fail% > 50% après 50+ requêtes |
| Prometheus | `/metrics` endpoint texte pour Grafana |
| Webhooks | POST sur pause/resume/alert events |
| Health check | Vérification connexion internet au démarrage |

## Classes clés

| Classe | Fichier | Rôle |
|--------|---------|------|
| `SharedMetrics` | `metrics.py` | Métriques partagées : request_log, domain_stats, tld_counts, category_counts, timing_heatmap, fingerprint_score(), pause/resume |
| `RequestLogEntry` | `metrics.py` | namedtuple pour le log de requêtes |
| `FetchResult` | `fetch_client.py` | Résultat HTTP avec status, html, bytes_received, error_msg, is_client_error, is_server_error |
| `DnsCache` | `dns_resolver.py` | Cache DNS TTL-aware avec IP persistence (dnspython) |
| `MetricsCollector` | `dashboard_collector.py` | Agrège stats crawlers → JSON, feature control, settings persistence, TLD filter, user add/remove |
| `UserCrawler` | `crawler.py` | Crawl par utilisateur virtuel avec queue, semaphore, rate limiting |
| `UserProfile` | `profiles.py` | Profil utilisateur : UA, geo, mobile, schedule, stealth headers, fingerprint rotation |

## Headers obligatoires (tout fichier noisy_lib)
```python
# nom.py - But en 5 mots
# IN: x | OUT: y | MODIFIE: z
# APPELÉ PAR: a | APPELLE: b
```

## Pattern logging uniforme
```python
log = logging.getLogger(__name__)

async def ma_fonction(x):
    log.info(f"[DEBUT] ma_fonction | {x=}")
    try:
        result = ...
        log.info(f"[FIN] ma_fonction | {result=}")
        return result
    except Exception as e:
        log.error(f"[ERREUR] ma_fonction | {e}")
        raise
```

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
- Blocklist = 2 niveaux : `domain_blocklist` (set, O(1), 766K+ OISD) + `url_blacklist` (list, substring, ~30 patterns)
- `_host_in_blocklist()` vérifie hostname + tous domaines parents (a.b.com → b.com → com)
- Fingerprint rotation toutes les 15-60 min par user (Accept, Cache-Control, Sec-CH-UA, DNT)
- Cookie jar `unsafe=True` par crawler — simule persistance cookies cross-domain
- Settings auto-sauvegardées dans `.noisy_settings.json` à chaque changement dashboard

## Stealth features

| Feature | Détail |
|---------|--------|
| TLS JA3 rotation | 6 cipher suite orderings, roté toutes 15-60min, `tls_profiles.py` |
| Realistic depth | 60% bounce/25% short/15% deep, mobile cap=3, `depth_model.py` |
| Referer chains | 40% search/30% direct/20% social/10% cross-site, `referer_chain.py` |
| Asset fetching | 2-5 img/css/js par page, Range headers partiels, `asset_fetcher.py` |
| Cookie persistence | Sérialisation JSON par user, `--cookie-persist`, `cookie_store.py` |
| Bandwidth throttle | Token bucket (fiber/4G/ADSL/3G), auto-assign mobile/desktop, `throttle.py` |
| WebSocket noise | 2-5 connexions idle (Binance/Kraken/Twitch), `--ws-workers`, `ws_noise.py` |
| Traffic mirror | Observation cache DNS système, bruit proportionnel, `--mirror`, `traffic_mirror.py` |
| Scheduler | Active hours `--schedule 8-23`, wrap-around supporté (22-6) |
| Geo profiles | 21 locales (Accept-Language + tz_offset), `--geo europe_fr` |
| Mobile sim | 10 mobile UAs, Sec-CH-UA-Mobile, depth réduit, `--mobile-ratio 0.3` |
| Search noise | Requêtes Google/Bing/DDG/Yahoo avec mots aléatoires, suit 1-3 résultats |
| Traffic replay | Import JSON/TXT historique navigateur, mixé avec CRUX |
| Stealth headers | 15+ combos Accept/Cache/Sec-Fetch/DNT, rotation par session |
| Fingerprint rotation | Accept/Cache/Sec-CH-UA + TLS cipher toutes 15-60min |
| Diurnal activity | Modèle 24h réaliste (pic midi, creux nuit), toggle on/off |
| Domain categories | 11 catégories (news, social, tech…), tracking + visualisation |
| Auto-pause | Pause auto si fail% > 50% après 50+ requêtes |
| OISD blocklists | NSFW (404K) + phishing/malware (362K) domaines bloqués |
| TLD/Region filter | 6 régions prédéfinies + TLD custom, appliqué live |
| Settings persistence | .noisy_settings.json restauré au redémarrage |
| Connection health | Vérification internet au démarrage |
| DNS TTL cache | dnspython résolution avec respect TTL, pas de re-query avant expiry, `dns_resolver.py` |
| DNS→TCP→TLS correlation | Chaque DNS resolve suivi de TCP+TLS handshake réel avec payload, `workers.py` |
| IP persistence | 1 IP par domaine pendant durée TTL (pas de round-robin churn), `dns_resolver.py` |
| DNS prefetch | Extraction domaines depuis liens page, burst DNS+TCP+TLS (comme Chrome), `dns_prefetch.py` |
| Mode léger (dns-optimized) | Connection:close, 64KB max body, 1 retry, skip assets, `fetch_client.py`+`crawler.py` |
| 3rd-party burst | 8-25 CDN/tracker/ad domains résolus en parallèle par page (effet iceberg), `dns_stealth.py` |
| Background app noise | NTP/Spotify/WhatsApp/Discord/Steam DNS bruit continu, `dns_stealth.py` |
| Micro-bursting | 30-60 queries simultanées puis silence 10-120s (pattern humain), `dns_stealth.py` |
| NXDOMAIN probes | Chrome intranet redirect detector + captive portal checks, `dns_stealth.py` |
| Range payload anti-DPI | GET+Range 4-12KB réel au lieu de HEAD 0-byte (défait heuristiques DPI), `dns_prefetch.py` |
| ALPN negotiation | h2+http/1.1 dans TLS raw sockets, http/1.1 only pour aiohttp, `tls_profiles.py` |
| ECH | Encrypted Client Hello via curl_cffi/BoringSSL (masque SNI du FAI), `ech_client.py` |
| Streaming noise | Connexions longues CDN vidéo, chunks 128-512KB avec délais (simule vidéo), `stream_noise.py` |

## Statut projet
- **Refactoring P0→P4** : terminé
- **Code review + 8 bug fixes** : terminé
- **Modularity audit + 6 refactors** : terminé
- **9 nouvelles features stealth** : terminé (TLS JA3, depth model, referer chains, asset fetch, cookies, throttle, WS noise, traffic mirror, crawler split)
- **Dashboard temps réel** : terminé (30+ fonctionnalités)
- **Audit sécurité** : terminé (bind local, HEAD-only noise, input validation, URL scheme validation)
- **3 bugfixes post-features** : `randint(2,1)` asset_fetcher, queue 4-tuple dashboard, features propagation collector
- **DNS stealth layer (5 features)** : terminé (TTL cache, DNS→TCP→TLS correlation, prefetch, lightweight mode, IP persistence)
- **DNS advanced stealth (4 features)** : terminé (3rd-party burst, background noise, micro-burst, NXDOMAIN probes)
- **Anti-DPI hardening (4+1 features)** : terminé (Range payload, ECH, streaming noise, IP persistence, ALPN)
- **ALPN h2 bugfix critique** : `_build_default_context()` doit être http/1.1 only (aiohttp incompatible h2 framing)
- **Tests** : 67 tests, tous verts, < 1s
- **Fork** : github.com/amartidandqdq/noisy (forked from madereddy/noisy)
- **⚠ dashboard_collector.py** : 501 lignes (god-object assumé, seule exception au max 180)

## Décisions clés

| Décision | Choix | Raison |
|----------|-------|--------|
| Rate limiting | 1 `DomainRateLimiter` partagé entre tous crawlers | Évite que 5 users frappent le même domaine simultanément |
| Retry HTTP | Uniquement 5xx + exceptions réseau, pas 4xx | 4xx = erreur client intentionnelle, pas transitoire |
| Blacklist URL | Double filtre : avant fetch + après extraction | Économise requêtes ET évite d'enqueue des URLs inutiles |
| Domain locks | Bounded dict 50K + FIFO eviction | Évite memory leak sur longues sessions |
| Config file | `--config` explicite, pas d'auto-load | Comportement prévisible |
| Dashboard stack | FastAPI + WebSocket + vanilla HTML/CSS/JS | Pas de build step, un seul fichier HTML |
| Metrics catégorisation | 4xx/5xx/network séparés | Évite inflation artificielle du fail% (4xx ≠ panne) |
| HTTP noise | HEAD only (pas POST) | Lecture seule, aucun effet secondaire sur les serveurs cibles |
| Dashboard bind | 127.0.0.1 par défaut | Pas d'auth, donc pas d'exposition réseau |
| Domain health threshold | 20% min, 10 samples min | Évite skip prématuré + permet recovery |
| Blocklist 2 niveaux | domain_blocklist (set) + url_blacklist (list) | O(1) pour 766K domaines OISD, substring pour patterns courts |
| TLD generic passthrough | .com/.net/.org toujours inclus | Filtre TLD ne bloque pas les sites internationaux sur gTLD |
| Settings persistence | JSON file, pas DB | Simple, portable, pas de dépendance |
| Feature tags cliquables | Toggle on/off direct dans dashboard | UX rapide sans formulaire |
| ALPN par contexte | http/1.1 only (aiohttp default), h2+http/1.1 (raw sockets rotated) | aiohttp ne supporte pas HTTP/2 framing → 400 sur tous les fetches si h2 négocié |
| dnspython pour DNS | dnspython au lieu de stdlib getaddrinfo | getaddrinfo n'expose pas le TTL, indispensable pour cache TTL-aware |
| curl_cffi pour ECH | curl_cffi (BoringSSL) au lieu de ssl stdlib | Python ssl n'a aucun support ECH, curl_cffi négocie ECH nativement |
| IP persistence | Stocker toutes les IPs mais retourner toujours la 1ère | Browsers font pareil — évite le round-robin churn détectable par DPI |
| Range payload | GET+Range 4-12KB au lieu de HEAD 0-byte | HEAD sans payload = pattern scan détectable par DPI |
