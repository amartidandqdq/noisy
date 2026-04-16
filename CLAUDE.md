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

## Architecture — 1 fichier = 1 responsabilité

```
noisy.py                  → Orchestration + entry point (130 lignes)
noisy_lib/
  config.py               → Toutes les constantes (65 lignes)
  config_loader.py        → Parser CLI + validation + lecture JSON (105 lignes)
  structures.py           → LRUSet / BoundedDict / TTLDict (90 lignes)
  profiles.py             → UserProfile / UAPool / diurnal model (120 lignes)
  extractor.py            → Extraction liens HTML + blacklist (45 lignes)
  fetchers.py             → Fetch CRUX sites + user agents (100 lignes)
  rate_limiter.py         → Délai inter-requêtes par domaine (55 lignes)
  fetch_client.py         → HTTP GET avec retry exponentiel (75 lignes)
  crawler.py              → UserCrawler + SharedMetrics (310 lignes)
  workers.py              → DNS noise / stats / UA refresh / HEAD noise (125 lignes)
  dashboard.py            → FastAPI + WebSocket dashboard server (280 lignes)
  static/dashboard.html   → Single-file dashboard UI (500 lignes)
start.bat                 → Windows one-click launcher
start.command             → macOS one-click launcher
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
| Stats ou bruit DNS/HEAD | `workers.py` |
| Dashboard web / API / métriques | `dashboard.py` + `static/dashboard.html` |
| Métriques agrégées cross-crawler | `crawler.py` (SharedMetrics) |

## Dashboard — fonctionnalités

| Catégorie | Détail |
|-----------|--------|
| Métriques | visited, failed, RPS, queued, unique URLs, active domains, bandwidth |
| Erreurs | 4xx / 5xx / network errors par user |
| Live log | 50 dernières requêtes avec status codes |
| Top domains | Top 20 par trafic avec health score |
| TLD distribution | Chart geo-diversity (.com, .fr, .jp…) |
| Diurnal curve | Modèle 24h avec marqueur position courante |
| Stealth score | Fingerprint (domain diversity, timing variance) |
| Contrôles | Pause/resume crawling, dark/light theme |
| Config editor | min_sleep, max_sleep, depth, domain_delay live |
| Export | JSON snapshot complet des métriques |
| Alertes | Bannière si fail% > seuil |
| Prometheus | `/metrics` endpoint texte pour Grafana |
| Webhooks | POST sur pause/resume/alert events |

## Classes clés ajoutées

| Classe | Fichier | Rôle |
|--------|---------|------|
| `SharedMetrics` | `crawler.py` | Métriques partagées : request_log, domain_stats, tld_counts, fingerprint_score(), pause/resume |
| `FetchResult` | `fetch_client.py` | Résultat HTTP avec status, html, bytes_received, error_msg, is_client_error, is_server_error |
| `MetricsCollector` | `dashboard.py` | Agrège stats crawlers → JSON pour dashboard + Prometheus |
| `RequestLogEntry` | `crawler.py` | namedtuple pour le log de requêtes |

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

## Statut projet
- **Refactoring P0→P4** : terminé
- **Dashboard temps réel** : terminé (16 fonctionnalités)
- **Audit sécurité** : terminé (bind local, HEAD-only noise, input validation, URL scheme validation)
- **Tests** : 67 tests, tous verts, < 0.5s
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
