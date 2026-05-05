# CrossFit Competition Tracker

Automated CrossFit competition tracking and Google Calendar synchronization.  
Scrapes [Reppi.fi](https://reppi.fi) and additional sources for upcoming competitions,  
then syncs them to a shared Google Calendar.

**Active Calendar:** *Urheilutapahtumat*  
**Sync Method:** Service Account (non-expiring) with OAuth fallback

---

## Directory Structure

```
crossfit-agent/
├── src/                     # Source code
│   ├── main.py              # CLI entry point (search, sync, full pipeline)
│   ├── scraper.py           # Competition aggregator
│   ├── reppi_scraper.py     # Reppi.fi scraper + international competitions
│   ├── calendar_sync.py     # Google Calendar sync (SA + OAuth)
│   └── test_reppi_scraper.py
├── scripts/                 # Operational scripts
│   ├── cron_runner.py       # Cron wrapper (circuit breaker, retry, logging)
│   └── update_cron_jobs.py  # Cron job configuration helper
├── data/                    # Runtime data
│   ├── competitions.json    # Scraped competitions
│   ├── state.json           # Last run state
│   ├── cron_state.json      # Cron job state
│   └── logs/                # Run logs
├── tests/                   # Tests
│   └── test_smoke.py
├── docs/                    # Documentation
│   └── SA_SETUP.md          # Service Account setup guide
├── venv/                    # Python 3.12 virtual environment
├── .env.example             # Environment variable template
├── requirements.txt         # Python dependencies
└── README.md
```

---

## Quick Start

### 1. Clone & Setup

```bash
git clone <repo-url>
cd crossfit-agent
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Service Account Configuration

The project uses a **Service Account + Public Key Upload** approach (Google's 2026 best practice —
no downloadable JSON key file, the private key never leaves your machine).

**Required environment variables:**

| Variable | Description |
|---|---|
| `SA_EMAIL` | Service Account email address |
| `SA_PROJECT_ID` | Google Cloud project ID |
| `SA_PRIVATE_KEY_ID` | 40-character hex key ID (from Cloud Console) |
| `CALENDAR_ID` | Google Calendar ID to sync to |

Copy `.env.example` to `.env` and fill in the values.
The script falls back to interactive OAuth if SA env vars are not set.

### 3. Calendar Setup

The SA must have write access to the target calendar:
1. Open [Google Calendar](https://calendar.google.com)
2. Find **Urheilutapahtumat** → **Settings and sharing** → **Share with specific people**
3. Add `crossfit-agent-calendar@<project-id>.iam.gserviceaccount.com` with **Make changes to events** permission

### 4. Manual Run

```bash
source venv/bin/activate

# Search for competitions
python src/main.py search

# Sync to Google Calendar
python src/main.py sync

# Full pipeline (search + sync)
python src/main.py full

# Run with enhanced cron wrapper
python scripts/cron_runner.py full
```

### 5. Run Tests

```bash
source venv/bin/activate
python tests/test_smoke.py
python src/test_reppi_scraper.py
```

---

## Cron Scheduling

The project is designed for scheduled execution via Hermes Agent cron jobs.
The `scripts/cron_runner.py` wrapper provides:

- **Circuit breaker** — halts after 3 consecutive failures to prevent API spam
- **Exponential backoff** — retries with 2s, 4s, 8s delays
- **Error categorization** — NETWORK, API, PARSING, AUTH, CONFIG, DEPENDENCY
- **Error logging** — last 100 errors persisted to `data/error_log.json`
- **Status command** — `python scripts/cron_runner.py status`

Recommended schedule:

| Job | Time | Purpose |
|---|---|---|
| `crossfit-search` | 02:00 daily | Scrape competitions |
| `crossfit-sync` | 03:00 daily | Sync to calendar |
| `crossfit-status` | 08:00 daily | Health check |

---

## Commands Reference

```bash
source venv/bin/activate

# Core pipeline
python src/main.py search        # Scrape competitions
python src/main.py sync          # Sync to Google Calendar
python src/main.py full          # Search + sync

# Cron wrapper (enhanced fault tolerance)
python scripts/cron_runner.py search
python scripts/cron_runner.py sync
python scripts/cron_runner.py full

# Health & debugging
python scripts/cron_runner.py status   # Circuit breaker state + stats
python scripts/cron_runner.py errors   # Last 100 errors
```

---

## Authentication Details

### Primary: Service Account (recommended for cron)

- Uses **private.pem** RSA key for JWT signing
- Key ID uploaded to Google Cloud Console as X.509 certificate
- **No token expiry** — suitable for unattended cron jobs
- **No downloadable JSON key** — private key never leaves your machine
- Activated when `SA_EMAIL` and `SA_PRIVATE_KEY_ID` env vars are set

### Fallback: OAuth (for development)

- Interactive browser-based flow
- Exchanges OAuth code for refresh token
- Token stored in `token.json`
- Refresh tokens **expire after 30 days of inactivity** — not suitable for cron

---

## Dependencies

- **Python 3.12+**
- `beautifulsoup4` — HTML parsing
- `requests` — HTTP client
- `google-api-python-client` — Google Calendar API
- `google-auth` — Service Account JWT authentication
- `google-auth-oauthlib` — OAuth flow (fallback)

Full list in `requirements.txt`.

---

## Security Notes

- `private.pem` is **never committed** — listed in `.gitignore`
- `credentials.json` and `token.json` are **never committed**
- `.env` is **never committed** — use `.env.example` as a template
- The private key has `chmod 600` permissions
- Service Account has access to only one calendar (principle of least privilege)

---

## Feature Status

- [x] Reppi.fi scraper (multi-strategy: API → requests → fallback)
- [x] International competition tracking
- [x] Google Calendar sync (create, update, dedup)
- [x] Service Account authentication (non-expiring)
- [x] Circuit breaker + exponential backoff
- [x] Error categorization and logging
- [x] Cron-ready execution
- [ ] Event update logic (currently creates, doesn't update changed events)
- [ ] Notification alerts on sync failures

---

**Last updated:** 2026-05-05
