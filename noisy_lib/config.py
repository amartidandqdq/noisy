# config.py - Toutes constantes du projet
# IN: rien | OUT: constantes importées | MODIFIE: rien
# APPELÉ PAR: tous modules | APPELLE: rien

# ---- CRUX ----
CRUX_TOP_CSV = "https://raw.githubusercontent.com/zakird/crux-top-lists/main/data/global/current.csv.gz"
DEFAULT_CRUX_COUNT = 10_000
DEFAULT_CRUX_REFRESH_DAYS = 31

# ---- USER AGENT POOL ----
UA_PAGE_URL = "https://www.useragents.me"
DEFAULT_UA_COUNT = 50
DEFAULT_UA_REFRESH_DAYS = 7

# ---- CRAWLER ----
DEFAULT_MAX_QUEUE_SIZE = 100_000
DEFAULT_MAX_DEPTH = 5
DEFAULT_THREADS = 10
DEFAULT_NUM_USERS = 5
DEFAULT_MAX_LINKS_PER_PAGE = 50

# ---- TIMING ----
DEFAULT_MIN_SLEEP = 2
DEFAULT_MAX_SLEEP = 15
DEFAULT_DOMAIN_DELAY = 5.0
DEFAULT_DNS_MIN_SLEEP = 5
DEFAULT_DNS_MAX_SLEEP = 30

# ---- CONNEXIONS (par user) ----
DEFAULT_TOTAL_CONNECTIONS = 40
DEFAULT_CONNECTIONS_PER_HOST = 4
DEFAULT_KEEPALIVE_TIMEOUT = 30
DNS_CACHE_TTL = 120

# ---- RÉSEAU ----
REQUEST_TIMEOUT = 15
MAX_RESPONSE_BYTES = 512 * 1024
MAX_HEADER_SIZE = 32 * 1024

# ---- RUNTIME ----
DEFAULT_RUN_TIMEOUT_SECONDS = None
SECONDS_PER_DAY = 24 * 60 * 60
DEFAULT_DNS_WORKERS = 3

# ---- DNS TTL ----
DNS_TTL_MIN = 60       # TTL minimum force (secondes) — evite re-requetes trop frequentes
DNS_TTL_MAX = 86400    # TTL max cap (24h)

# ---- DNS PREFETCH ----
DEFAULT_PREFETCH_WORKERS = 0
PREFETCH_MAX_DOMAINS = 20      # max domaines extraits par page pour prefetch
PREFETCH_MIN_SLEEP = 30
PREFETCH_MAX_SLEEP = 90
PREFETCH_MAX_BODY = 65_536     # 64KB — assez pour extraire les liens

# ---- THIRD-PARTY DOMAINS (CDN, trackers, pubs, media, infra) ----
THIRD_PARTY_DOMAINS = [
    # CDN
    "fonts.googleapis.com", "fonts.gstatic.com", "cdn.jsdelivr.net",
    "cdnjs.cloudflare.com", "ajax.googleapis.com", "unpkg.com",
    "stackpath.bootstrapcdn.com", "maxcdn.bootstrapcdn.com",
    # Analytics / Trackers
    "www.google-analytics.com", "analytics.google.com",
    "googletagmanager.com", "www.googletagmanager.com",
    "connect.facebook.net", "www.facebook.com",
    "pixel.facebook.com", "bat.bing.com",
    "static.hotjar.com", "snap.licdn.com",
    # Pubs
    "pagead2.googlesyndication.com", "securepubads.g.doubleclick.net",
    "tpc.googlesyndication.com", "adservice.google.com",
    "criteo.com", "static.criteo.net", "cdn.taboola.com",
    "cdn.outbrain.com", "amazon-adsystem.com",
    # Media
    "i.ytimg.com", "yt3.ggpht.com", "play.google.com",
    "platform.twitter.com", "abs.twimg.com",
    # Infra (OCSP, CRL, updates)
    "ocsp.digicert.com", "ocsp.pki.goog", "crl.globalsign.com",
    "clients1.google.com", "update.googleapis.com",
]
THIRD_PARTY_PER_PAGE_MIN = 8
THIRD_PARTY_PER_PAGE_MAX = 25

# ---- BACKGROUND APP DOMAINS (systeme, NTP, apps communes) ----
BACKGROUND_APP_DOMAINS = [
    # NTP / Systeme
    "time.windows.com", "time.apple.com", "time.google.com",
    "ntp.ubuntu.com", "pool.ntp.org",
    # Verification connectivite
    "www.msftconnecttest.com", "dns.msftncsi.com",
    "connectivitycheck.gstatic.com", "captive.apple.com",
    "detectportal.firefox.com", "connectivity-check.ubuntu.com",
    # Mises a jour
    "update.microsoft.com", "download.windowsupdate.com",
    "officecdn.microsoft.com", "go.microsoft.com",
    # Apps communes
    "api.spotify.com", "apresolve.spotify.com", "spclient.wg.spotify.com",
    "web.whatsapp.com", "mmg.whatsapp.net", "static.whatsapp.net",
    "discord.com", "gateway.discord.gg", "cdn.discordapp.com",
    "steamcommunity.com", "store.steampowered.com", "api.steampowered.com",
    "signal.org", "textsecure-service.whispersystems.org",
    "outlook.office365.com", "login.microsoftonline.com",
    "push.services.mozilla.com", "safebrowsing.googleapis.com",
]
BACKGROUND_MIN_SLEEP = 30
BACKGROUND_MAX_SLEEP = 180

# ---- MICRO-BURST ----
BURST_SIZE_MIN = 30
BURST_SIZE_MAX = 60
BURST_SILENCE_MIN = 10    # secondes de silence apres burst
BURST_SILENCE_MAX = 120
BURST_INTRA_DELAY = 0.02  # 20ms entre requetes dans un burst

# ---- NXDOMAIN / CAPTIVE PORTAL ----
CAPTIVE_PORTAL_DOMAINS = [
    "connectivitycheck.gstatic.com",  # Android / Chrome
    "captive.apple.com",               # macOS / iOS
    "detectportal.firefox.com",         # Firefox
    "www.msftconnecttest.com",          # Windows
    "dns.msftncsi.com",                 # Windows legacy
]
NXDOMAIN_PROBE_INTERVAL = (300, 900)   # 5-15 min entre sondes Chrome
CAPTIVE_PORTAL_INTERVAL = (600, 1800)  # 10-30 min entre checks portail

# ---- PROBE PAYLOAD (anti-DPI) ----
PROBE_RANGE_MIN = 4096     # 4KB min Range payload
PROBE_RANGE_MAX = 12288    # 12KB max Range payload

# ---- STREAMING CDN (long-lived chunked GET — simule pattern streaming) ----
# NOTE: les domaines "Generic CDN" ne sont pas video — ils servent a ouvrir
# une connexion longue avec Range request. Le but est le pattern reseau
# (chunks reguliers, keep-alive), pas le contenu video reel.
STREAMING_CDN_DOMAINS = [
    # YouTube CDN (domaines generiques — les vrais ont des suffixes dynamiques)
    "redirector.googlevideo.com", "manifest.googlevideo.com",
    # Twitch
    "usher.ttvnw.net", "static.twitchcdn.net",
    # Generic CDN — package CDN, sert juste a maintenir une connexion longue
    "cdn.jsdelivr.net", "cdnjs.cloudflare.com",
    "ajax.googleapis.com", "fonts.gstatic.com",
    "cdn.cloudflare.com", "unpkg.com",
]
STREAM_CHUNK_SIZE = (131_072, 524_288)   # 128KB-512KB par chunk
STREAM_CHUNK_DELAY = (1.0, 3.0)          # secondes entre chunks (simule buffering)
STREAM_SESSION_DURATION = (60, 300)      # 1-5 min par "visionnage"
STREAM_PAUSE = (30, 120)                 # pause entre sessions streaming

# ---- CACHE ----
DEFAULT_VISITED_MAX = 500_000

# ---- RETRY ----
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0

# ---- DASHBOARD ----
DEFAULT_DASHBOARD_PORT = 8080
DASHBOARD_UPDATE_INTERVAL = 2
DEFAULT_POST_NOISE_WORKERS = 1
ALERT_FAIL_THRESHOLD = 30.0  # % failure rate to trigger alert
AUTO_PAUSE_FAIL_THRESHOLD = 50.0  # % failure rate to auto-pause
AUTO_PAUSE_MIN_REQUESTS = 50  # minimum requests before auto-pause kicks in
WEBHOOK_TIMEOUT = 10

# ---- TLD / RÉGION ----
GENERIC_TLDS = {"com", "net", "org", "edu", "gov", "io", "dev", "app", "co"}

REGION_PRESETS = {
    "europe": {"fr", "de", "uk", "es", "it", "nl", "be", "ch", "at", "pt",
               "pl", "cz", "se", "no", "dk", "fi", "ie", "ro", "gr", "hu"},
    "asia": {"jp", "kr", "cn", "tw", "hk", "sg", "th", "my", "id", "ph",
             "vn", "in", "pk", "bd"},
    "americas": {"br", "mx", "ar", "cl", "co", "pe", "ca", "us"},
    "africa": {"za", "ng", "ke", "eg", "ma", "tn", "gh"},
    "oceania": {"au", "nz"},
    "middle_east": {"ae", "sa", "il", "tr", "qa", "kw"},
}

# ---- SCHEDULER ----
DEFAULT_SCHEDULE = None  # (start_hour, end_hour) ou None = toujours actif

# ---- MOBILE ----
DEFAULT_MOBILE_RATIO = 0.3

# ---- SEARCH NOISE ----
DEFAULT_SEARCH_WORKERS = 0
SEARCH_ENGINES = [
    "https://www.google.com/search?q={query}",
    "https://www.bing.com/search?q={query}",
    "https://duckduckgo.com/?q={query}",
    "https://search.yahoo.com/search?p={query}",
]
SEARCH_WORDS = [
    "best", "how", "what", "review", "buy", "price", "weather", "news", "recipe",
    "travel", "hotel", "restaurant", "movie", "music", "book", "game", "sport",
    "health", "fitness", "diet", "car", "phone", "laptop", "software", "app",
    "tutorial", "guide", "tips", "free", "online", "store", "shop", "discount",
    "coffee", "machine", "garden", "house", "rent", "job", "salary", "school",
    "university", "course", "language", "history", "science", "technology",
    "fashion", "style", "design", "art", "photo", "video", "streaming", "podcast",
    "cooking", "baking", "wine", "beer", "hiking", "camping", "yoga", "meditation",
    "dog", "cat", "pet", "plant", "flower", "furniture", "insurance", "bank",
    "crypto", "stock", "investment", "startup", "marketing", "SEO", "blog",
    "email", "calendar", "productivity", "remote", "work", "meeting", "team",
    "birthday", "gift", "wedding", "holiday", "vacation", "flight", "airport",
    "train", "bus", "bike", "electric", "solar", "recycling", "volunteer",
    "museum", "concert", "festival", "theater", "park", "beach", "mountain",
    "running", "swimming", "cycling", "football", "basketball", "tennis",
    "pizza", "sushi", "pasta", "salad", "smoothie", "breakfast", "dinner",
    "weather", "forecast", "tomorrow", "weekend", "tonight", "near me",
]

# ---- DOMAIN CATEGORIES ----
DOMAIN_CATEGORIES = {
    "news": ["cnn.com", "bbc.com", "reuters.com", "nytimes.com", "theguardian.com",
             "lemonde.fr", "spiegel.de", "elpais.com", "corriere.it", "nhk.or.jp",
             "foxnews.com", "washingtonpost.com", "bloomberg.com", "aljazeera.com",
             "news.yahoo.com", "news.google.com", "apnews.com", "france24.com"],
    "social": ["facebook.com", "twitter.com", "x.com", "instagram.com", "linkedin.com",
               "reddit.com", "tiktok.com", "pinterest.com", "tumblr.com", "mastodon.social",
               "threads.net", "snapchat.com", "discord.com", "twitch.tv"],
    "ecommerce": ["amazon.com", "ebay.com", "aliexpress.com", "walmart.com", "etsy.com",
                  "shopify.com", "zalando.com", "rakuten.co.jp", "mercadolibre.com",
                  "target.com", "bestbuy.com", "ikea.com", "asos.com"],
    "tech": ["github.com", "stackoverflow.com", "medium.com", "dev.to", "hackernews.com",
             "techcrunch.com", "theverge.com", "arstechnica.com", "wired.com",
             "slashdot.org", "producthunt.com", "gitlab.com", "digitalocean.com"],
    "education": ["wikipedia.org", "wikimedia.org", "khanacademy.org", "coursera.org",
                  "edx.org", "udemy.com", "scholar.google.com", "academia.edu",
                  "britannica.com", "quora.com", "stackexchange.com"],
    "finance": ["yahoo.com/finance", "bloomberg.com", "cnbc.com", "marketwatch.com",
                "investing.com", "tradingview.com", "coinmarketcap.com", "binance.com"],
    "entertainment": ["youtube.com", "netflix.com", "spotify.com", "twitch.tv",
                      "imdb.com", "rottentomatoes.com", "soundcloud.com", "vimeo.com",
                      "disneyplus.com", "hulu.com", "crunchyroll.com"],
    "travel": ["booking.com", "airbnb.com", "tripadvisor.com", "expedia.com",
               "skyscanner.com", "kayak.com", "hotels.com", "google.com/travel"],
    "health": ["webmd.com", "mayoclinic.org", "healthline.com", "nih.gov",
               "who.int", "medlineplus.gov", "cdc.gov"],
    "sports": ["espn.com", "bbc.com/sport", "sports.yahoo.com", "nba.com", "fifa.com",
               "uefa.com", "nfl.com", "flashscore.com", "goal.com"],
    "government": [".gov", ".gouv.fr", ".gov.uk", ".gob.mx", ".gov.br", ".go.jp"],
}

def categorize_domain(domain: str) -> str:
    """Retourne la catégorie d'un domaine, ou 'other'."""
    for cat, patterns in DOMAIN_CATEGORIES.items():
        for p in patterns:
            if p in domain:
                return cat
    return "other"

# ---- GEO PROFILES ----
GEO_PROFILES = {
    "europe_fr": {"lang": "fr-FR,fr;q=0.9,en;q=0.5", "tz_offset": 1},
    "europe_de": {"lang": "de-DE,de;q=0.9,en;q=0.5", "tz_offset": 1},
    "europe_es": {"lang": "es-ES,es;q=0.9,en;q=0.5", "tz_offset": 1},
    "europe_it": {"lang": "it-IT,it;q=0.9,en;q=0.5", "tz_offset": 1},
    "europe_uk": {"lang": "en-GB,en;q=0.9", "tz_offset": 0},
    "europe_nl": {"lang": "nl-NL,nl;q=0.9,en;q=0.5", "tz_offset": 1},
    "europe_pl": {"lang": "pl-PL,pl;q=0.9,en;q=0.3", "tz_offset": 1},
    "europe_pt": {"lang": "pt-PT,pt;q=0.9,en;q=0.5", "tz_offset": 0},
    "europe_se": {"lang": "sv-SE,sv;q=0.9,en;q=0.5", "tz_offset": 1},
    "americas_us": {"lang": "en-US,en;q=0.9", "tz_offset": -5},
    "americas_br": {"lang": "pt-BR,pt;q=0.9,en;q=0.5", "tz_offset": -3},
    "americas_mx": {"lang": "es-MX,es;q=0.9,en;q=0.3", "tz_offset": -6},
    "americas_ca": {"lang": "en-CA,en;q=0.9,fr;q=0.5", "tz_offset": -5},
    "asia_jp": {"lang": "ja-JP,ja;q=0.9,en;q=0.3", "tz_offset": 9},
    "asia_kr": {"lang": "ko-KR,ko;q=0.9,en;q=0.3", "tz_offset": 9},
    "asia_cn": {"lang": "zh-CN,zh;q=0.9,en;q=0.3", "tz_offset": 8},
    "asia_in": {"lang": "hi-IN,hi;q=0.9,en;q=0.7", "tz_offset": 5},
    "middle_east_ae": {"lang": "ar-AE,ar;q=0.9,en;q=0.5", "tz_offset": 4},
    "middle_east_tr": {"lang": "tr-TR,tr;q=0.9,en;q=0.3", "tz_offset": 3},
    "africa_za": {"lang": "en-ZA,en;q=0.9,af;q=0.5", "tz_offset": 2},
    "oceania_au": {"lang": "en-AU,en;q=0.9", "tz_offset": 10},
}

# ---- MOBILE UAs ----
MOBILE_UA_POOL = [
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; SM-S928B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SM-A546B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Pixel 7a) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_3_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/122.0.6261.89 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_7_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; SAMSUNG SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/23.0 Chrome/115.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; 22101316G) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPad; CPU OS 17_3_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Mobile/15E148 Safari/604.1",
]

# ---- FALLBACK UAs ----
UA_FALLBACK = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.3; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Safari/605.1.15",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36",
]

# ---- BLOCKLISTS OISD ----
OISD_NSFW_URL = "https://nsfw.oisd.nl/domainswild2"
OISD_BIG_URL = "https://big.oisd.nl/domainswild2"

# ---- URL BLACKLIST ----
DEFAULT_URL_BLACKLIST = [
    # ---- navigation/technique ----
    "t.co", "t.umblr.com", "messenger.com", "itunes.apple.com",
    "l.facebook.com", "bit.ly", "mediawiki",
    ".css", ".ico", ".xml", ".json", ".png", ".iso", ".pdf", ".zip", ".exe", ".dmg",
    "intent/tweet", "twitter.com/share", "dialog/feed?",
    "zendesk", "clickserve",
    "logout", "signout", "sign-out", "log-out",
    "javascript:", "mailto:", "tel:",
    # ---- TLD adultes ----
    ".xxx", ".porn", ".sex", ".adult",
]
