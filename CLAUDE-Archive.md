# CLAUDE.md Archive

Contenu archivé depuis CLAUDE.md pour maintenir l'efficacité du contexte.
Référence historique uniquement — voir CLAUDE.md pour l'état courant.

---

## Archived: 2026-04-16

### Stealth features — table détaillée (avant compression en groupes)

| Feature | Détail |
|---------|--------|
| TLS JA3 rotation | 6 cipher suite orderings, roté toutes 15-60min, `tls_profiles.py` |
| Realistic depth | bounce 50-70% / short 20-30% / deep remainder (re-tirée par session), mobile cap=3, `depth_model.py` |
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

### Statut projet — historique complet

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
- **ALPN h2 bugfix (2 passes)** : 1) `_build_default_context()` http/1.1 only, 2) `get_rotated_ssl_context(include_h2=False)` default — rotated contexts via `profiles.py` passaient encore h2 à aiohttp
- **Settings persistence fix** : `_save_settings({"features": data})` écrasait tout → remplacé par `_get_all_features_state()` qui sauvegarde l'état complet
- **Dashboard cleanup** : Timing Heatmap + RPS History supprimés (HTML, CSS, JS)
- **Code review + 11 fixes (post-DNS stealth)** : terminé (socket leak try/finally x4, dead imports, get_running_loop, dedicated DNS executor, ECH docstring, STREAMING_CDN comment, random→rng, [FIN] logs, +9 smoke tests)
- **Dashboard refonte A+D** : terminé (sidebar 6 onglets, file split static/{css,js}/, keyboard shortcuts 1-6 + P/T/D, dense mode, persistent state localStorage, Cache-Control no-cache)
- **Bug fixes UX** : geo/schedule/diurnal hérités par `add_user()`, `is_mobile_ua()` détecté de l'UA (plus de "desktop + UA iPhone"), depth_model en fourchettes par session

---
