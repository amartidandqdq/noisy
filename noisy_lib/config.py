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
