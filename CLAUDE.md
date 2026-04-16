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
noisy.py                  → Orchestration + entry point (281 lignes)
noisy_lib/
  __init__.py             → Utilitaires partagés: host_in_blocklist, extract_tld (19 lignes)
  config.py               → TOUTES constantes + données pures: geo, UAs, catégories (218 lignes)
  config_loader.py        → Parser CLI + validation + lecture JSON (138 lignes)
  structures.py           → LRUSet / BoundedDict / TTLDict (90 lignes)
  metrics.py              → SharedMetrics cross-crawler (127 lignes)
  profiles.py             → UserProfile / UAPool / stealth headers / diurnal (200 lignes)
  extractor.py            → Extraction liens HTML + blacklist (54 lignes)
  fetchers.py             → Fetch CRUX / UAs / OISD blocklists / history (169 lignes)
  rate_limiter.py         → Délai inter-requêtes par domaine (54 lignes)
  fetch_client.py         → HTTP GET avec retry exponentiel (74 lignes)
  crawler.py              → UserCrawler uniquement (213 lignes)
  workers.py              → DNS / stats / UA refresh / HEAD / search noise (181 lignes)
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
  ← metrics.py ← config
  ← profiles.py ← config
  ← rate_limiter.py ← config, structures
  ← fetch_client.py ← config, profiles
  ← extractor.py ← __init__
  ← fetchers.py ← config, profiles
  ← crawler.py ← metrics, config, extractor, fetch_client, profiles, rate_limiter, structures
  ← workers.py ← __init__, config, fetchers, profiles
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
| Scheduler | Active hours `--schedule 8-23`, wrap-around supporté (22-6) |
| Geo profiles | 21 locales (Accept-Language + tz_offset), `--geo europe_fr` |
| Mobile sim | 10 mobile UAs, Sec-CH-UA-Mobile, depth réduit, `--mobile-ratio 0.3` |
| Search noise | Requêtes Google/Bing/DDG/Yahoo avec mots aléatoires, suit 1-3 résultats |
| Traffic replay | Import JSON/TXT historique navigateur, mixé avec CRUX |
| Stealth headers | 15+ combos Accept/Cache/Sec-Fetch/DNT, rotation par session |
| Fingerprint rotation | Changement Accept/Cache/Sec-CH-UA toutes 15-60min |
| Diurnal activity | Modèle 24h réaliste (pic midi, creux nuit), toggle on/off |
| Domain categories | 11 catégories (news, social, tech…), tracking + visualisation |
| Auto-pause | Pause auto si fail% > 50% après 50+ requêtes |
| OISD blocklists | NSFW (404K) + phishing/malware (362K) domaines bloqués |
| TLD/Region filter | 6 régions prédéfinies + TLD custom, appliqué live |
| Settings persistence | .noisy_settings.json restauré au redémarrage |
| Connection health | Vérification internet au démarrage |

## Statut projet
- **Refactoring P0→P4** : terminé
- **Dashboard temps réel** : terminé (30+ fonctionnalités)
- **Stealth features** : terminé (14 features, toutes contrôlables depuis dashboard)
- **Audit sécurité** : terminé (bind local, HEAD-only noise, input validation, URL scheme validation)
- **Tests** : 67 tests, tous verts, < 1s
- **Fork** : github.com/amartidandqdq/noisy (forked from madereddy/noisy)

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
