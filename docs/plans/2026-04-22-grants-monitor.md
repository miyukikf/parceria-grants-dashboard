# Parcería Grants Monitor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an automated weekly grants monitor that scrapes 9 funding sites, deduplicates against a Google Sheet, emails a summary, and displays opportunities in a GitHub Pages dashboard.

**Architecture:** A Python script (`monitor.py`) handles OAuth 2.0 auth, per-site scraping, Sheet deduplication, and Gmail notification. A static `dashboard/index.html` reads the Sheet via the public gviz/tq JSON endpoint (no auth needed — requires sheet to be "Anyone with link can view"). A launchd `.plist` triggers the script every Monday at 08:00.

**Tech Stack:** Python 3.11+, gspread, google-auth-oauthlib, requests, beautifulsoup4, smtplib (stdlib), vanilla JS + CSS in a single HTML file, launchd (macOS)

---

## Pre-Flight Checklist (do before Task 1)

- [ ] Have `credentials.json` (OAuth 2.0 Desktop app) ready to copy into the project folder
- [ ] Know your Gmail address and Gmail App Password
- [ ] Open your Google Sheet → Share → "Anyone with the link" → Viewer (enables dashboard)
- [ ] Note your Sheet's first-row column headers (assumed below — adjust if different)

**Assumed existing Sheet columns:**
`Nombre | Entidad | Monto | Fecha_Cierre | URL | Descripcion`

**Columns the script will add if missing:**
`Entidad_Parceria | Estado | Urgencia | Consorcio_Requerido | Socio_Consorcio | Fecha_Verificada | Link_Propuesta`

---

## File Map

| File | Responsibility |
|------|---------------|
| `monitor.py` | Orchestrator: auth → scrape → deduplicate → write sheet → send email |
| `scrapers.py` | One parser function per site, plus keyword filter |
| `sheets.py` | gspread wrapper: read rows, ensure columns exist, append rows |
| `email_notify.py` | SMTP email builder + sender via Gmail App Password |
| `dashboard/index.html` | Static dashboard — fetches Sheet via gviz JSON, renders cards |
| `com.parceria.monitor.plist` | launchd job definition (weekly Monday 08:00) |
| `requirements.txt` | Pinned Python dependencies |
| `.env` | `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `NOTIFY_TO` (never commit) |
| `.env.example` | Safe template to commit |
| `README.md` | Full deployment + run instructions |

---

## Task 1: Project Scaffold & Dependencies

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `.gitignore`

- [ ] **Step 1: Create `requirements.txt`**

```
gspread==6.1.2
google-auth==2.29.0
google-auth-oauthlib==1.2.0
google-api-python-client==2.126.0
requests==2.31.0
beautifulsoup4==4.12.3
python-dotenv==1.0.1
```

- [ ] **Step 2: Create `.env.example`**

```
GMAIL_USER=tu@gmail.com
GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
NOTIFY_TO=tu@gmail.com
SHEET_ID=1dU2Tep3gakBNDPR5zRJdth_MDb5X_TVUratBgmQESHg
```

- [ ] **Step 3: Create `.gitignore`**

```
.env
credentials.json
token.json
logs/
__pycache__/
*.pyc
```

- [ ] **Step 4: Install dependencies**

```bash
cd "/Users/miyukikasahara/documents/Parceria Dashboard"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Expected: all packages install without error.

- [ ] **Step 5: Copy your credentials.json into the project root**

```bash
# Example — adjust source path to wherever you downloaded it
cp ~/Downloads/credentials.json "/Users/miyukikasahara/documents/Parceria Dashboard/credentials.json"
```

- [ ] **Step 6: Create your `.env` from the example**

```bash
cp .env.example .env
# Then open .env and fill in real values
```

- [ ] **Step 7: Commit scaffold**

```bash
git init
git add requirements.txt .env.example .gitignore
git commit -m "chore: project scaffold for Parcería grants monitor"
```

---

## Task 2: Google Sheets Auth Module (`sheets.py` — auth section)

**Files:**
- Create: `sheets.py`

- [ ] **Step 1: Write `sheets.py` with auth + column management**

```python
# sheets.py
import logging
from pathlib import Path
import gspread
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
CREDS_FILE = Path(__file__).parent / "credentials.json"
TOKEN_FILE = Path(__file__).parent / "token.json"

# Columns the monitor manages (added if not present)
MONITOR_COLUMNS = [
    "Entidad_Parceria",
    "Estado",
    "Urgencia",
    "Consorcio_Requerido",
    "Socio_Consorcio",
    "Fecha_Verificada",
    "Link_Propuesta",
]

def get_authenticated_client() -> gspread.Client:
    """Return an authenticated gspread client, refreshing/creating token as needed."""
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            logger.info("OAuth token refreshed.")
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
            logger.info("New OAuth token obtained via browser.")

        TOKEN_FILE.write_text(creds.to_json())

    return gspread.authorize(creds)


def open_sheet(client: gspread.Client, sheet_id: str) -> gspread.Worksheet:
    """Open the first worksheet of the given Sheet ID."""
    spreadsheet = client.open_by_key(sheet_id)
    return spreadsheet.sheet1


def ensure_columns(ws: gspread.Worksheet) -> dict:
    """
    Ensure all MONITOR_COLUMNS exist as headers.
    Returns a dict mapping column_name -> 1-based column index.
    """
    headers = ws.row_values(1)
    col_map = {h: i + 1 for i, h in enumerate(headers)}

    for col_name in MONITOR_COLUMNS:
        if col_name not in col_map:
            next_col = len(headers) + 1
            ws.update_cell(1, next_col, col_name)
            col_map[col_name] = next_col
            headers.append(col_name)
            logger.info(f"Added column: {col_name} at position {next_col}")

    return col_map


def get_existing_urls(ws: gspread.Worksheet) -> set:
    """Return a set of all URLs already recorded in the sheet (deduplication key)."""
    records = ws.get_all_records()
    urls = set()
    for row in records:
        url = row.get("URL") or row.get("url") or row.get("Url") or ""
        if url:
            urls.add(url.strip())
    return urls


def append_opportunity(ws: gspread.Worksheet, col_map: dict, opp: dict) -> None:
    """
    Append a single opportunity dict as a new row.
    opp keys: nombre, entidad, monto, fecha_cierre, url, descripcion,
               entidad_parceria, estado, urgencia, consorcio_requerido,
               socio_consorcio, fecha_verificada, link_propuesta
    """
    # Build row aligned to current headers
    headers = ws.row_values(1)
    row = [""] * len(headers)

    field_map = {
        "Nombre": opp.get("nombre", ""),
        "Entidad": opp.get("entidad", ""),
        "Monto": opp.get("monto", ""),
        "Fecha_Cierre": opp.get("fecha_cierre", ""),
        "URL": opp.get("url", ""),
        "Descripcion": opp.get("descripcion", ""),
        "Entidad_Parceria": opp.get("entidad_parceria", "Todos"),
        "Estado": opp.get("estado", "Identificado"),
        "Urgencia": opp.get("urgencia", ""),
        "Consorcio_Requerido": opp.get("consorcio_requerido", "Por confirmar"),
        "Socio_Consorcio": opp.get("socio_consorcio", ""),
        "Fecha_Verificada": opp.get("fecha_verificada", ""),
        "Link_Propuesta": opp.get("link_propuesta", ""),
    }

    for col_name, value in field_map.items():
        if col_name in col_map:
            row[col_map[col_name] - 1] = value

    ws.append_row(row, value_input_option="USER_ENTERED")
    logger.info(f"Appended: {opp.get('nombre', 'unnamed')} ({opp.get('url', '')})")
```

- [ ] **Step 2: Smoke-test auth manually**

```bash
source .venv/bin/activate
python3 -c "
from sheets import get_authenticated_client
import os; from dotenv import load_dotenv; load_dotenv()
client = get_authenticated_client()
ws = client.open_by_key(os.environ['SHEET_ID']).sheet1
print('Connected. First row:', ws.row_values(1))
"
```

Expected: browser opens for OAuth consent (first time only), then prints your Sheet's header row. `token.json` is created.

- [ ] **Step 3: Commit**

```bash
git add sheets.py
git commit -m "feat: Google Sheets OAuth auth + column management"
```

---

## Task 3: Web Scrapers (`scrapers.py`)

**Files:**
- Create: `scrapers.py`

Each scraper function receives a `requests.Session` and returns a list of opportunity dicts. If it fails, it logs and returns `[]`.

- [ ] **Step 1: Write `scrapers.py`**

```python
# scrapers.py
import logging
import re
from datetime import datetime
from typing import Optional
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}

KEYWORDS = [
    "género", "genero", "equidad", "mujeres", "mujer",
    "youth", "juventud", "jóvenes", "jovenes",
    "workforce", "digital", "inclusión", "inclusion",
    "esg", "sostenibilidad", "sustentabilidad",
    "impacto social", "caribe", "caribbean",
    "república dominicana", "dominican republic", "lac",
    "women", "gender", "equity",
]

def matches_keywords(text: str) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in KEYWORDS)


def safe_get(session: requests.Session, url: str, timeout: int = 15) -> Optional[BeautifulSoup]:
    try:
        resp = session.get(url, timeout=timeout, headers=HEADERS)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        logger.error(f"Failed to fetch {url}: {e}")
        return None


def make_opp(nombre: str, entidad: str, url: str,
             monto: str = "", fecha_cierre: str = "",
             descripcion: str = "", fuente: str = "") -> dict:
    return {
        "nombre": nombre.strip(),
        "entidad": entidad.strip(),
        "monto": monto.strip(),
        "fecha_cierre": fecha_cierre.strip(),
        "url": url.strip(),
        "descripcion": descripcion.strip()[:300],
        "fuente": fuente,
        "fecha_verificada": datetime.today().strftime("%Y-%m-%d"),
        "entidad_parceria": "Todos",
        "estado": "Identificado",
        "consorcio_requerido": "Por confirmar",
        "socio_consorcio": "",
        "link_propuesta": "",
        "urgencia": "",  # calculated later
    }


# ── Site parsers ────────────────────────────────────────────────────────────

def scrape_carib_export(session: requests.Session) -> list:
    """https://carib-export.com/opportunities/"""
    url = "https://carib-export.com/opportunities/"
    soup = safe_get(session, url)
    if not soup:
        return []

    results = []
    # Carib-Export lists opportunities as articles or list items
    for item in soup.select("article, .opportunity-item, .entry, li.opportunity"):
        title_el = item.select_one("h2, h3, h4, .title, a")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        link_el = item.select_one("a[href]")
        link = link_el["href"] if link_el else url
        if not link.startswith("http"):
            link = "https://carib-export.com" + link
        desc = item.get_text(" ", strip=True)[:300]
        if matches_keywords(title + " " + desc):
            results.append(make_opp(title, "Caribbean Export", link,
                                    descripcion=desc, fuente="carib-export.com"))
    logger.info(f"carib-export.com: {len(results)} matching opportunities")
    return results


def scrape_eulac(session: requests.Session) -> list:
    """https://eulacdigitalaccelerator.com"""
    url = "https://eulacdigitalaccelerator.com"
    soup = safe_get(session, url)
    if not soup:
        return []

    results = []
    for item in soup.select("article, .call-item, .program-card, section.opportunity"):
        title_el = item.select_one("h1, h2, h3, .title")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        link_el = item.select_one("a[href]")
        link = link_el["href"] if link_el else url
        if not link.startswith("http"):
            link = "https://eulacdigitalaccelerator.com" + link
        desc = item.get_text(" ", strip=True)[:300]
        if matches_keywords(title + " " + desc):
            results.append(make_opp(title, "EU-LAC Digital Accelerator", link,
                                    descripcion=desc, fuente="eulacdigitalaccelerator.com"))

    # Fallback: if no structured items found, treat the whole page as one opportunity
    if not results:
        title = soup.title.string if soup.title else "EU-LAC Digital Accelerator"
        results.append(make_opp(title, "EU-LAC Digital Accelerator", url,
                                descripcion="Verificar convocatorias activas en el sitio.",
                                fuente="eulacdigitalaccelerator.com"))
    logger.info(f"eulacdigitalaccelerator.com: {len(results)} matching opportunities")
    return results


def scrape_bidlab(session: requests.Session) -> list:
    """https://bidlab.org/en/calls"""
    url = "https://bidlab.org/en/calls"
    soup = safe_get(session, url)
    if not soup:
        return []

    results = []
    for item in soup.select(".call-card, article, .listing-item, li"):
        title_el = item.select_one("h2, h3, h4, .title, a")
        if not title_el or len(title_el.get_text(strip=True)) < 5:
            continue
        title = title_el.get_text(strip=True)
        link_el = item.select_one("a[href]")
        link = link_el["href"] if link_el else url
        if not link.startswith("http"):
            link = "https://bidlab.org" + link
        # Look for deadline
        date_el = item.select_one(".date, .deadline, time, [class*='date']")
        deadline = date_el.get_text(strip=True) if date_el else ""
        desc = item.get_text(" ", strip=True)[:300]
        if matches_keywords(title + " " + desc):
            results.append(make_opp(title, "BID Lab", link,
                                    fecha_cierre=deadline, descripcion=desc,
                                    fuente="bidlab.org"))
    logger.info(f"bidlab.org: {len(results)} matching opportunities")
    return results


def scrape_frida(session: requests.Session) -> list:
    """https://programafrida.net/convocatorias/"""
    url = "https://programafrida.net/convocatorias/"
    soup = safe_get(session, url)
    if not soup:
        return []

    results = []
    for item in soup.select("article, .convocatoria, .post, li.item"):
        title_el = item.select_one("h2, h3, .entry-title, a")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        link_el = item.select_one("a[href]")
        link = link_el["href"] if link_el else url
        desc = item.get_text(" ", strip=True)[:300]
        if matches_keywords(title + " " + desc):
            results.append(make_opp(title, "Programa FRIDA", link,
                                    descripcion=desc, fuente="programafrida.net"))
    logger.info(f"programafrida.net: {len(results)} matching opportunities")
    return results


def scrape_cartier(session: requests.Session) -> list:
    """https://www.cartierwomensinitiative.com/awards"""
    url = "https://www.cartierwomensinitiative.com/awards"
    soup = safe_get(session, url)
    if not soup:
        return []

    results = []
    for item in soup.select(".award-item, article, .program-block, section"):
        title_el = item.select_one("h2, h3, h4, .title")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if len(title) < 5:
            continue
        link_el = item.select_one("a[href]")
        link = link_el["href"] if link_el else url
        if not link.startswith("http"):
            link = "https://www.cartierwomensinitiative.com" + link
        desc = item.get_text(" ", strip=True)[:300]
        if matches_keywords(title + " " + desc):
            results.append(make_opp(title, "Cartier Women's Initiative", link,
                                    descripcion=desc, fuente="cartierwomensinitiative.com"))

    if not results:
        results.append(make_opp(
            "Cartier Women's Initiative Awards",
            "Cartier Women's Initiative", url,
            descripcion="Premio para mujeres emprendedoras con impacto social. Verificar apertura.",
            fuente="cartierwomensinitiative.com"
        ))
    logger.info(f"cartierwomensinitiative.com: {len(results)} matching opportunities")
    return results


def scrape_gdlab(session: requests.Session) -> list:
    """https://gdlab.iadb.org/en/call"""
    url = "https://gdlab.iadb.org/en/call"
    soup = safe_get(session, url)
    if not soup:
        return []

    results = []
    for item in soup.select(".call-card, article, .listing, li"):
        title_el = item.select_one("h2, h3, h4, .title, a")
        if not title_el or len(title_el.get_text(strip=True)) < 5:
            continue
        title = title_el.get_text(strip=True)
        link_el = item.select_one("a[href]")
        link = link_el["href"] if link_el else url
        if not link.startswith("http"):
            link = "https://gdlab.iadb.org" + link
        desc = item.get_text(" ", strip=True)[:300]
        if matches_keywords(title + " " + desc):
            results.append(make_opp(title, "GD Lab IADB", link,
                                    descripcion=desc, fuente="gdlab.iadb.org"))
    logger.info(f"gdlab.iadb.org: {len(results)} matching opportunities")
    return results


def scrape_caribank(session: requests.Session) -> list:
    """https://www.caribank.org/our-work/programmes/cultural-and-creative-industries-innovation-fund"""
    url = "https://www.caribank.org/our-work/programmes/cultural-and-creative-industries-innovation-fund"
    soup = safe_get(session, url)
    if not soup:
        return []

    results = []
    title_el = soup.select_one("h1, h2, .page-title")
    title = title_el.get_text(strip=True) if title_el else "CDB Cultural & Creative Industries Fund"
    desc_el = soup.select_one(".field-body, .page-description, p")
    desc = desc_el.get_text(" ", strip=True)[:300] if desc_el else ""
    if matches_keywords(title + " " + desc + " caribbean cultural creative"):
        results.append(make_opp(title, "Caribbean Development Bank", url,
                                descripcion=desc, fuente="caribank.org"))
    logger.info(f"caribank.org: {len(results)} matching opportunities")
    return results


def scrape_undp_do(session: requests.Session) -> list:
    """https://www.do.undp.org"""
    url = "https://www.do.undp.org"
    soup = safe_get(session, url)
    if not soup:
        return []

    results = []
    for item in soup.select("article, .news-item, .story-card, .call-item"):
        title_el = item.select_one("h2, h3, h4, .title, a")
        if not title_el or len(title_el.get_text(strip=True)) < 5:
            continue
        title = title_el.get_text(strip=True)
        link_el = item.select_one("a[href]")
        link = link_el["href"] if link_el else url
        if not link.startswith("http"):
            link = "https://www.do.undp.org" + link
        desc = item.get_text(" ", strip=True)[:300]
        if matches_keywords(title + " " + desc):
            results.append(make_opp(title, "UNDP República Dominicana", link,
                                    descripcion=desc, fuente="do.undp.org"))
    logger.info(f"do.undp.org: {len(results)} matching opportunities")
    return results


def scrape_goethe(session: requests.Session) -> list:
    """https://www.goethe.de/en/kul/foe/int.html"""
    url = "https://www.goethe.de/en/kul/foe/int.html"
    soup = safe_get(session, url)
    if not soup:
        return []

    results = []
    for item in soup.select(".m-program-teaser, article, .teaser, li.item"):
        title_el = item.select_one("h2, h3, h4, .title, a")
        if not title_el or len(title_el.get_text(strip=True)) < 5:
            continue
        title = title_el.get_text(strip=True)
        link_el = item.select_one("a[href]")
        link = link_el["href"] if link_el else url
        if not link.startswith("http"):
            link = "https://www.goethe.de" + link
        desc = item.get_text(" ", strip=True)[:300]
        if matches_keywords(title + " " + desc):
            results.append(make_opp(title, "Goethe Institut", link,
                                    descripcion=desc, fuente="goethe.de"))
    logger.info(f"goethe.de: {len(results)} matching opportunities")
    return results


# ── Main scrape runner ───────────────────────────────────────────────────────

SCRAPERS = [
    scrape_carib_export,
    scrape_eulac,
    scrape_bidlab,
    scrape_frida,
    scrape_cartier,
    scrape_gdlab,
    scrape_caribank,
    scrape_undp_do,
    scrape_goethe,
]


def run_all_scrapers() -> list:
    """Run all site scrapers and return combined list of opportunities."""
    session = requests.Session()
    session.headers.update(HEADERS)
    all_opps = []
    for scraper in SCRAPERS:
        try:
            opps = scraper(session)
            all_opps.extend(opps)
        except Exception as e:
            logger.error(f"Unhandled error in {scraper.__name__}: {e}")
    logger.info(f"Total scraped (before dedup): {len(all_opps)}")
    return all_opps
```

- [ ] **Step 2: Smoke-test scrapers**

```bash
source .venv/bin/activate
python3 -c "
import logging
logging.basicConfig(level=logging.INFO)
from scrapers import run_all_scrapers
results = run_all_scrapers()
print(f'Total results: {len(results)}')
for r in results[:5]:
    print(' -', r['nombre'][:60], '|', r['entidad'])
"
```

Expected: INFO logs per site, at least some results printed (count varies by what's live). Sites that fail log an error and continue — this is correct behavior.

- [ ] **Step 3: Commit**

```bash
git add scrapers.py
git commit -m "feat: web scrapers for 9 grant sites with keyword filtering"
```

---

## Task 4: Urgency Calculator

**Files:**
- Modify: `scrapers.py` (add helper at bottom)

- [ ] **Step 1: Add `calculate_urgency` function to `scrapers.py`**

Add after the `SCRAPERS` list:

```python
def calculate_urgency(fecha_cierre: str) -> str:
    """
    Returns 'Alta' (<14 days), 'Media' (<30 days), 'Baja' (>=30 days or unknown).
    Tries multiple date formats.
    """
    if not fecha_cierre or fecha_cierre.strip() == "":
        return "Baja"

    formats = [
        "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y",
        "%B %d, %Y", "%d %B %Y", "%d de %B de %Y",
        "%b %d, %Y", "%d %b %Y",
    ]
    today = datetime.today().date()
    for fmt in formats:
        try:
            deadline = datetime.strptime(fecha_cierre.strip(), fmt).date()
            days_left = (deadline - today).days
            if days_left < 14:
                return "Alta"
            elif days_left < 30:
                return "Media"
            else:
                return "Baja"
        except ValueError:
            continue

    return "Baja"  # unparseable date = treat as non-urgent
```

- [ ] **Step 2: Test urgency calculation**

```bash
python3 -c "
from scrapers import calculate_urgency
from datetime import date, timedelta

today = date.today()
in_7  = (today + timedelta(days=7)).strftime('%Y-%m-%d')
in_20 = (today + timedelta(days=20)).strftime('%Y-%m-%d')
in_45 = (today + timedelta(days=45)).strftime('%Y-%m-%d')

assert calculate_urgency(in_7)  == 'Alta',  'Expected Alta'
assert calculate_urgency(in_20) == 'Media', 'Expected Media'
assert calculate_urgency(in_45) == 'Baja',  'Expected Baja'
assert calculate_urgency('')    == 'Baja',  'Expected Baja for empty'
print('All urgency assertions passed.')
"
```

Expected: `All urgency assertions passed.`

- [ ] **Step 3: Commit**

```bash
git add scrapers.py
git commit -m "feat: urgency calculator from deadline date"
```

---

## Task 5: Email Notification Module (`email_notify.py`)

**Files:**
- Create: `email_notify.py`

- [ ] **Step 1: Write `email_notify.py`**

```python
# email_notify.py
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465


def _build_html(new_opps: list, sheet_id: str) -> str:
    """Build the HTML body for the summary email."""
    sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}"
    dashboard_url = "https://<tu-usuario>.github.io/parceria-grants-dashboard/"

    urgent = [o for o in new_opps if o.get("urgencia") == "Alta"]
    soon   = [o for o in new_opps if o.get("urgencia") == "Media"]

    def opp_row(o: dict) -> str:
        urgencia = o.get("urgencia", "Baja")
        color = {"Alta": "#e74c3c", "Media": "#f39c12", "Baja": "#27ae60"}.get(urgencia, "#888")
        return (
            f'<tr>'
            f'<td style="padding:8px;border-bottom:1px solid #eee">'
            f'<a href="{o["url"]}" style="color:#2D6A4F;font-weight:bold">{o["nombre"]}</a></td>'
            f'<td style="padding:8px;border-bottom:1px solid #eee">{o["entidad"]}</td>'
            f'<td style="padding:8px;border-bottom:1px solid #eee">{o.get("monto","")}</td>'
            f'<td style="padding:8px;border-bottom:1px solid #eee">{o.get("fecha_cierre","")}</td>'
            f'<td style="padding:8px;border-bottom:1px solid #eee;color:{color};font-weight:bold">{urgencia}</td>'
            f'</tr>'
        )

    all_rows = "".join(opp_row(o) for o in new_opps)

    urgent_section = ""
    if urgent or soon:
        urgent_rows = "".join(opp_row(o) for o in (urgent + soon))
        urgent_section = f"""
        <h2 style="color:#e74c3c">⚠️ Cierran en menos de 30 días</h2>
        <table width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr style="background:#f5f5f5">
            <th style="padding:8px;text-align:left">Nombre</th>
            <th style="padding:8px;text-align:left">Entidad</th>
            <th style="padding:8px;text-align:left">Monto</th>
            <th style="padding:8px;text-align:left">Cierre</th>
            <th style="padding:8px;text-align:left">Urgencia</th>
          </tr>
          {urgent_rows}
        </table>
        <br>
        """

    return f"""
    <html><body style="font-family:Arial,sans-serif;color:#333;max-width:800px;margin:0 auto">
      <div style="background:#2D6A4F;padding:20px;border-radius:8px 8px 0 0">
        <h1 style="color:#F4C430;margin:0">Parcería — Monitor de Fondos</h1>
        <p style="color:#fff;margin:4px 0">
          Reporte semanal · {datetime.today().strftime('%d %B %Y')}
        </p>
      </div>
      <div style="background:#f9f9f9;padding:20px;border-radius:0 0 8px 8px">

        <h2 style="color:#2D6A4F">
          {len(new_opps)} nueva{'s' if len(new_opps) != 1 else ''} oportunidad{'es' if len(new_opps) != 1 else ''} encontrada{'s' if len(new_opps) != 1 else ''}
        </h2>

        {urgent_section}

        <h2 style="color:#2D6A4F">Todas las nuevas oportunidades</h2>
        <table width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr style="background:#e8f5e9">
            <th style="padding:8px;text-align:left">Nombre</th>
            <th style="padding:8px;text-align:left">Entidad</th>
            <th style="padding:8px;text-align:left">Monto</th>
            <th style="padding:8px;text-align:left">Cierre</th>
            <th style="padding:8px;text-align:left">Urgencia</th>
          </tr>
          {all_rows if new_opps else '<tr><td colspan="5" style="padding:16px;color:#888">No se encontraron nuevas oportunidades esta semana.</td></tr>'}
        </table>

        <br>
        <div style="text-align:center;margin-top:24px">
          <a href="{sheet_url}"
             style="background:#2D6A4F;color:#fff;padding:10px 20px;border-radius:6px;text-decoration:none;margin-right:12px">
            Ver Google Sheet
          </a>
          <a href="{dashboard_url}"
             style="background:#F4C430;color:#333;padding:10px 20px;border-radius:6px;text-decoration:none">
            Ver Dashboard
          </a>
        </div>
      </div>
    </body></html>
    """


def send_summary_email(
    gmail_user: str,
    app_password: str,
    notify_to: str,
    new_opps: list,
    sheet_id: str,
) -> None:
    """Send the weekly summary email via Gmail SMTP with App Password."""
    if not gmail_user or not app_password:
        logger.error("Missing GMAIL_USER or GMAIL_APP_PASSWORD — skipping email.")
        return

    subject = (
        f"[Parcería] {len(new_opps)} nueva{'s' if len(new_opps) != 1 else ''} "
        f"oportunidad{'es' if len(new_opps) != 1 else ''} · "
        f"{datetime.today().strftime('%d/%m/%Y')}"
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = notify_to

    html_body = _build_html(new_opps, sheet_id)
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
            server.login(gmail_user, app_password)
            server.sendmail(gmail_user, notify_to, msg.as_string())
        logger.info(f"Summary email sent to {notify_to}")
    except smtplib.SMTPAuthenticationError:
        logger.error(
            "Gmail authentication failed. Check GMAIL_USER and GMAIL_APP_PASSWORD. "
            "Make sure 2FA is on and you used an App Password (not your account password)."
        )
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
```

- [ ] **Step 2: Commit**

```bash
git add email_notify.py
git commit -m "feat: Gmail summary email with urgency highlights"
```

---

## Task 6: Main Orchestrator (`monitor.py`)

**Files:**
- Create: `monitor.py`

- [ ] **Step 1: Write `monitor.py`**

```python
#!/usr/bin/env python3
# monitor.py — Parcería Grants Monitor
# Run manually: python3 monitor.py
# Scheduled via launchd (see com.parceria.monitor.plist)

import logging
import os
import sys
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

from scrapers import run_all_scrapers, calculate_urgency
from sheets import (
    get_authenticated_client,
    open_sheet,
    ensure_columns,
    get_existing_urls,
    append_opportunity,
)
from email_notify import send_summary_email

# ── Logging setup ────────────────────────────────────────────────────────────
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
log_file = LOG_DIR / f"monitor_{datetime.today().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


def main():
    load_dotenv()

    SHEET_ID      = os.environ.get("SHEET_ID", "1dU2Tep3gakBNDPR5zRJdth_MDb5X_TVUratBgmQESHg")
    GMAIL_USER    = os.environ.get("GMAIL_USER", "")
    GMAIL_PASS    = os.environ.get("GMAIL_APP_PASSWORD", "")
    NOTIFY_TO     = os.environ.get("NOTIFY_TO", GMAIL_USER)

    logger.info("=== Parcería Grants Monitor starting ===")

    # 1. Authenticate and open sheet
    logger.info("Authenticating with Google Sheets...")
    client = get_authenticated_client()
    ws = open_sheet(client, SHEET_ID)
    col_map = ensure_columns(ws)
    logger.info(f"Sheet opened. Column map: {list(col_map.keys())}")

    # 2. Get existing URLs (deduplication)
    existing_urls = get_existing_urls(ws)
    logger.info(f"Existing opportunities in sheet: {len(existing_urls)}")

    # 3. Scrape all sites
    logger.info("Starting web scraping...")
    scraped = run_all_scrapers()

    # 4. Filter new + calculate urgency
    new_opps = []
    for opp in scraped:
        url = opp.get("url", "").strip()
        if not url or url in existing_urls:
            continue
        opp["urgencia"] = calculate_urgency(opp.get("fecha_cierre", ""))
        new_opps.append(opp)

    logger.info(f"New opportunities to add: {len(new_opps)}")

    # 5. Write new rows to sheet
    for opp in new_opps:
        try:
            append_opportunity(ws, col_map, opp)
        except Exception as e:
            logger.error(f"Failed to write to sheet: {opp.get('nombre')} — {e}")

    # 6. Send email summary
    logger.info("Sending email summary...")
    send_summary_email(GMAIL_USER, GMAIL_PASS, NOTIFY_TO, new_opps, SHEET_ID)

    logger.info(f"=== Done. {len(new_opps)} new opportunities added. Log: {log_file} ===")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x monitor.py
```

- [ ] **Step 3: First full test run**

```bash
source .venv/bin/activate
python3 monitor.py
```

Expected:
- Browser opens once for OAuth (creates `token.json`)
- INFO logs for each site scraped
- Any new opportunities appear in your Google Sheet
- Email arrives in your inbox

- [ ] **Step 4: Commit**

```bash
git add monitor.py
git commit -m "feat: main monitor orchestrator — scrape, dedup, write sheet, email"
```

---

## Task 7: Dashboard (`dashboard/index.html`)

**Files:**
- Create: `dashboard/index.html`

The dashboard fetches your Sheet's data using the **gviz/tq JSON endpoint** — no API key needed, only requires the sheet to be publicly viewable.

- [ ] **Step 1: Verify your sheet is publicly viewable**

Open your Google Sheet → Share → change to "Anyone with the link" → Viewer. This is required for the dashboard to work.

- [ ] **Step 2: Write `dashboard/index.html`**

```html
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Parcería — Dashboard de Fondos</title>
  <style>
    :root {
      --verde: #2D6A4F;
      --amarillo: #F4C430;
      --gris: #4A4A4A;
      --verde-claro: #e8f5e9;
      --rojo: #e74c3c;
      --naranja: #f39c12;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Segoe UI', Arial, sans-serif; background: #f5f7f5; color: var(--gris); }

    /* ── Header ── */
    header {
      background: var(--verde);
      padding: 20px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 12px;
    }
    header h1 { color: var(--amarillo); font-size: 1.6rem; }
    header p  { color: #cde8d6; font-size: 0.85rem; margin-top: 2px; }
    #last-updated { color: #afd9be; font-size: 0.78rem; text-align: right; }

    /* ── Controls ── */
    .controls {
      background: #fff;
      padding: 16px 24px;
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      border-bottom: 2px solid var(--verde-claro);
      position: sticky;
      top: 0;
      z-index: 10;
      box-shadow: 0 2px 6px rgba(0,0,0,0.06);
    }
    .controls input, .controls select {
      padding: 8px 12px;
      border: 1px solid #ddd;
      border-radius: 6px;
      font-size: 0.9rem;
      outline: none;
      transition: border-color 0.2s;
    }
    .controls input:focus, .controls select:focus { border-color: var(--verde); }
    #search { flex: 1; min-width: 200px; }
    .stat-chip {
      background: var(--verde-claro);
      color: var(--verde);
      padding: 8px 14px;
      border-radius: 20px;
      font-size: 0.85rem;
      font-weight: 600;
      white-space: nowrap;
    }

    /* ── Grid ── */
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
      gap: 18px;
      padding: 24px;
    }

    /* ── Cards ── */
    .card {
      background: #fff;
      border-radius: 10px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.08);
      overflow: hidden;
      cursor: pointer;
      transition: transform 0.15s, box-shadow 0.15s;
      display: flex;
      flex-direction: column;
    }
    .card:hover { transform: translateY(-3px); box-shadow: 0 6px 18px rgba(0,0,0,0.13); }

    .card-urgency-bar { height: 5px; }
    .urgency-alta   .card-urgency-bar { background: var(--rojo); }
    .urgency-media  .card-urgency-bar { background: var(--naranja); }
    .urgency-baja   .card-urgency-bar, .urgency-default .card-urgency-bar { background: var(--verde); }

    .card-body { padding: 16px; flex: 1; }
    .card-title {
      font-size: 1rem;
      font-weight: 700;
      color: var(--verde);
      margin-bottom: 6px;
      line-height: 1.3;
    }
    .card-entidad { font-size: 0.8rem; color: #888; margin-bottom: 10px; }
    .card-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 10px;
    }
    .badge {
      font-size: 0.72rem;
      padding: 3px 8px;
      border-radius: 12px;
      font-weight: 600;
    }
    .badge-estado    { background: #e3f2fd; color: #1565c0; }
    .badge-urgencia  { color: #fff; }
    .badge-alta      { background: var(--rojo); }
    .badge-media     { background: var(--naranja); }
    .badge-baja      { background: var(--verde); }
    .badge-entidad-p { background: #fff3cd; color: #856404; }

    .card-footer {
      padding: 10px 16px;
      background: #fafafa;
      border-top: 1px solid #f0f0f0;
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 0.78rem;
      color: #999;
    }
    .card-monto { color: var(--gris); font-weight: 600; }

    /* ── Empty state ── */
    .empty {
      grid-column: 1 / -1;
      text-align: center;
      padding: 60px 20px;
      color: #aaa;
    }
    .empty p { font-size: 1.1rem; margin-top: 8px; }

    /* ── Loading ── */
    #loading {
      text-align: center;
      padding: 60px;
      color: var(--verde);
      font-size: 1.1rem;
    }

    /* ── Responsive ── */
    @media (max-width: 600px) {
      header { padding: 14px 16px; }
      header h1 { font-size: 1.2rem; }
      .controls { padding: 12px 16px; }
      .grid { padding: 14px; gap: 14px; }
    }
  </style>
</head>
<body>

<header>
  <div>
    <h1>Parcería — Dashboard de Fondos</h1>
    <p>Monitor automático de oportunidades de financiamiento</p>
  </div>
  <div id="last-updated">Cargando...</div>
</header>

<div class="controls">
  <input type="text" id="search" placeholder="Buscar por nombre o entidad...">
  <select id="filter-estado">
    <option value="">Todos los estados</option>
    <option>Identificado</option>
    <option>En preparación</option>
    <option>Enviado</option>
    <option>Aprobado</option>
    <option>Rechazado</option>
  </select>
  <select id="filter-entidad-p">
    <option value="">Todas las entidades</option>
    <option>Parcería</option>
    <option>Fundación</option>
    <option>Gina</option>
    <option>Todos</option>
  </select>
  <select id="filter-urgencia">
    <option value="">Todas las urgencias</option>
    <option value="Alta">Alta (menos de 14 días)</option>
    <option value="Media">Media (menos de 30 días)</option>
    <option value="Baja">Baja / Sin fecha</option>
  </select>
  <span class="stat-chip" id="count-chip">0 oportunidades</span>
</div>

<div id="loading">Cargando oportunidades...</div>
<div class="grid" id="grid" style="display:none"></div>

<script>
  // ── Config ──────────────────────────────────────────────────────────────
  const SHEET_ID = "1dU2Tep3gakBNDPR5zRJdth_MDb5X_TVUratBgmQESHg";
  const GVIZ_URL = `https://docs.google.com/spreadsheets/d/${SHEET_ID}/gviz/tq?tqx=out:json`;

  // ── State ───────────────────────────────────────────────────────────────
  let allOpps = [];

  // ── Fetch & parse gviz response ─────────────────────────────────────────
  async function loadData() {
    try {
      const res = await fetch(GVIZ_URL);
      const text = await res.text();
      // gviz wraps JSON in: google.visualization.Query.setResponse({...})
      const json = JSON.parse(text.substring(text.indexOf('{'), text.lastIndexOf('}') + 1));
      const cols = json.table.cols.map(c => c.label);
      const rows = json.table.rows || [];

      allOpps = rows.map(row => {
        const obj = {};
        cols.forEach((col, i) => {
          const cell = row.c[i];
          obj[col] = cell ? (cell.f || cell.v || "") : "";
        });
        return obj;
      }).filter(o => o["Nombre"] || o["nombre"] || o["URL"] || o["url"]);

      document.getElementById("last-updated").textContent =
        `Última carga: ${new Date().toLocaleString('es-DO')}`;

      renderCards(filterOpps());
      document.getElementById("loading").style.display = "none";
      document.getElementById("grid").style.display = "grid";
    } catch (e) {
      document.getElementById("loading").textContent =
        "Error al cargar datos. Asegúrate de que el Sheet es público.";
      console.error(e);
    }
  }

  // ── Normalize field names (handles lowercase/uppercase variants) ──────
  function f(opp, ...keys) {
    for (const k of keys) {
      if (opp[k] !== undefined && opp[k] !== "") return opp[k];
      // Try capitalized
      const cap = k.charAt(0).toUpperCase() + k.slice(1);
      if (opp[cap] !== undefined && opp[cap] !== "") return opp[cap];
    }
    return "";
  }

  // ── Urgency class ────────────────────────────────────────────────────────
  function urgencyClass(urgencia) {
    const u = (urgencia || "").toLowerCase();
    if (u === "alta")  return "urgency-alta";
    if (u === "media") return "urgency-media";
    if (u === "baja")  return "urgency-baja";
    return "urgency-default";
  }

  function urgencyBadgeClass(urgencia) {
    const u = (urgencia || "").toLowerCase();
    if (u === "alta")  return "badge-alta";
    if (u === "media") return "badge-media";
    return "badge-baja";
  }

  // ── Render ───────────────────────────────────────────────────────────────
  function renderCards(opps) {
    const grid = document.getElementById("grid");
    const chip = document.getElementById("count-chip");

    chip.textContent = `${opps.length} oportunidad${opps.length !== 1 ? "es" : ""}`;

    if (opps.length === 0) {
      grid.innerHTML = `<div class="empty">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#ccc" stroke-width="1.5">
          <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
        </svg>
        <p>No se encontraron oportunidades con esos filtros.</p>
      </div>`;
      return;
    }

    grid.innerHTML = opps.map(opp => {
      const nombre    = f(opp, "Nombre", "nombre") || "(Sin nombre)";
      const entidad   = f(opp, "Entidad", "entidad");
      const monto     = f(opp, "Monto", "monto");
      const cierre    = f(opp, "Fecha_Cierre", "fecha_cierre");
      const estado    = f(opp, "Estado", "estado") || "Identificado";
      const urgencia  = f(opp, "Urgencia", "urgencia") || "";
      const entidadP  = f(opp, "Entidad_Parceria", "entidad_parceria");
      const url       = f(opp, "URL", "url");

      const uClass = urgencyClass(urgencia);
      const uBadge = urgencyBadgeClass(urgencia);

      return `
        <div class="card ${uClass}" onclick="${url ? `window.open('${url.replace(/'/g,"\\'")}','_blank')` : ''}">
          <div class="card-urgency-bar"></div>
          <div class="card-body">
            <div class="card-title">${escHtml(nombre)}</div>
            <div class="card-entidad">${escHtml(entidad)}</div>
            <div class="card-meta">
              ${estado    ? `<span class="badge badge-estado">${escHtml(estado)}</span>` : ""}
              ${urgencia  ? `<span class="badge badge-urgencia ${uBadge}">${escHtml(urgencia)}</span>` : ""}
              ${entidadP  ? `<span class="badge badge-entidad-p">${escHtml(entidadP)}</span>` : ""}
            </div>
          </div>
          <div class="card-footer">
            <span>${cierre ? "Cierre: " + escHtml(cierre) : "Sin fecha de cierre"}</span>
            <span class="card-monto">${monto ? escHtml(monto) : ""}</span>
          </div>
        </div>`;
    }).join("");
  }

  function escHtml(str) {
    return String(str)
      .replace(/&/g,"&amp;").replace(/</g,"&lt;")
      .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
  }

  // ── Filter ───────────────────────────────────────────────────────────────
  function filterOpps() {
    const q        = document.getElementById("search").value.toLowerCase();
    const estado   = document.getElementById("filter-estado").value;
    const entidadP = document.getElementById("filter-entidad-p").value;
    const urgencia = document.getElementById("filter-urgencia").value;

    return allOpps.filter(opp => {
      const nombre  = (f(opp,"Nombre","nombre") + " " + f(opp,"Entidad","entidad")).toLowerCase();
      if (q && !nombre.includes(q)) return false;

      const oEstado = f(opp,"Estado","estado");
      if (estado && oEstado !== estado) return false;

      const oEP = f(opp,"Entidad_Parceria","entidad_parceria");
      if (entidadP && oEP !== entidadP) return false;

      const oUrg = f(opp,"Urgencia","urgencia");
      if (urgencia && oUrg !== urgencia) return false;

      return true;
    });
  }

  // ── Event listeners ──────────────────────────────────────────────────────
  ["search","filter-estado","filter-entidad-p","filter-urgencia"].forEach(id => {
    document.getElementById(id).addEventListener("input", () => renderCards(filterOpps()));
  });

  // ── Init ─────────────────────────────────────────────────────────────────
  loadData();
</script>
</body>
</html>
```

- [ ] **Step 3: Test dashboard locally**

```bash
open "/Users/miyukikasahara/documents/Parceria Dashboard/dashboard/index.html"
```

Expected: dashboard loads in browser, shows cards from your Sheet. If you see "Error al cargar datos", verify the Sheet is set to public (anyone with the link can view).

- [ ] **Step 4: Commit dashboard**

```bash
git add dashboard/index.html
git commit -m "feat: responsive grants dashboard with urgency semaphore and filters"
```

---

## Task 8: launchd Cron Job

**Files:**
- Create: `com.parceria.monitor.plist`

- [ ] **Step 1: Write the `.plist` file**

Replace `YOUR_USERNAME` with your macOS username (run `whoami` to check).

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.parceria.monitor</string>

  <key>ProgramArguments</key>
  <array>
    <string>/Users/YOUR_USERNAME/documents/Parceria Dashboard/.venv/bin/python3</string>
    <string>/Users/YOUR_USERNAME/documents/Parceria Dashboard/monitor.py</string>
  </array>

  <key>WorkingDirectory</key>
  <string>/Users/YOUR_USERNAME/documents/Parceria Dashboard</string>

  <key>StartCalendarInterval</key>
  <dict>
    <key>Weekday</key>
    <integer>1</integer>
    <key>Hour</key>
    <integer>8</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>

  <key>StandardOutPath</key>
  <string>/Users/YOUR_USERNAME/documents/Parceria Dashboard/logs/launchd_stdout.log</string>

  <key>StandardErrorPath</key>
  <string>/Users/YOUR_USERNAME/documents/Parceria Dashboard/logs/launchd_stderr.log</string>

  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>

  <key>RunAtLoad</key>
  <false/>
</dict>
</plist>
```

- [ ] **Step 2: Install the launchd job**

```bash
# Get your username
whoami

# Edit the plist replacing YOUR_USERNAME, then copy to LaunchAgents
cp "com.parceria.monitor.plist" ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.parceria.monitor.plist

# Verify it's loaded
launchctl list | grep parceria
```

Expected: `launchctl list` shows `com.parceria.monitor` in the output.

- [ ] **Step 3: Commit plist (with YOUR_USERNAME replaced)**

```bash
git add com.parceria.monitor.plist
git commit -m "chore: launchd plist for weekly Monday 8am monitoring"
```

---

## Task 9: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`**

```markdown
# Parcería Grants Monitor

Sistema automático de monitoreo de oportunidades de fondos para Parcería (República Dominicana).

## Estructura

```
Parceria Dashboard/
  monitor.py              ← Script principal (scraping + Sheet + email)
  scrapers.py             ← Parsers por sitio web
  sheets.py               ← Integración Google Sheets (OAuth)
  email_notify.py         ← Envío de email vía Gmail App Password
  dashboard/
    index.html            ← Dashboard estático (GitHub Pages)
  credentials.json        ← Poner aquí manualmente (NO commitear)
  token.json              ← Se genera automáticamente (NO commitear)
  .env                    ← Variables de entorno (NO commitear)
  .env.example            ← Plantilla segura para compartir
  com.parceria.monitor.plist ← Cron job (launchd, macOS)
  logs/                   ← Logs automáticos
  requirements.txt
```

## Requisitos Previos

- Python 3.11+
- Cuenta de Google con acceso al Sheet ID: `1dU2Tep3gakBNDPR5zRJdth_MDb5X_TVUratBgmQESHg`
- Gmail con verificación en 2 pasos activada
- App Password de Gmail (no es tu contraseña normal)

## Setup inicial

### 1. Configurar `credentials.json`

1. Ve a [Google Cloud Console](https://console.cloud.google.com)
2. Descarga el `credentials.json` de OAuth 2.0 (tipo: Desktop app)
3. Cópialo aquí: `Parceria Dashboard/credentials.json`
   ```bash
   cp ~/Downloads/credentials.json "/Users/TU_USUARIO/documents/Parceria Dashboard/credentials.json"
   ```

### 2. Configurar variables de entorno

```bash
cd "/Users/TU_USUARIO/documents/Parceria Dashboard"
cp .env.example .env
```

Abre `.env` y rellena:
```
GMAIL_USER=tu@gmail.com
GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
NOTIFY_TO=tu@gmail.com
SHEET_ID=1dU2Tep3gakBNDPR5zRJdth_MDb5X_TVUratBgmQESHg
```

**¿Cómo conseguir un App Password?**
1. Gmail → Cuenta → Seguridad → Verificación en 2 pasos → Contraseñas de aplicación
2. Crea una con nombre "Parceria Monitor"
3. Copia el código de 16 caracteres

### 3. Instalar dependencias

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. Hacer el Sheet público (para el dashboard)

Google Sheet → Compartir → "Cualquier persona con el enlace" → Lector

### 5. Primer run manual

```bash
source .venv/bin/activate
python3 monitor.py
```

La primera vez, se abrirá el navegador para autorizar el acceso a Google Sheets. Acepta con tu cuenta de Google. Se creará `token.json` automáticamente.

## Activar el cron job (macOS)

```bash
# Edita com.parceria.monitor.plist: reemplaza YOUR_USERNAME con tu usuario
whoami  # ← usa este valor

cp com.parceria.monitor.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.parceria.monitor.plist

# Verificar que está activo
launchctl list | grep parceria
```

Corre automáticamente cada **lunes a las 8:00am**.

**Para desactivarlo:**
```bash
launchctl unload ~/Library/LaunchAgents/com.parceria.monitor.plist
```

**Para correrlo manualmente ahora:**
```bash
launchctl start com.parceria.monitor
```

## Dashboard en GitHub Pages

1. Sube el repositorio a GitHub (al repo `parceria-grants-dashboard`)
2. Ve a Settings → Pages → Source: `main` branch, carpeta `/dashboard`
3. El dashboard estará en: `https://TU_USUARIO.github.io/parceria-grants-dashboard/`
4. Actualiza la URL del dashboard en `email_notify.py` (línea `dashboard_url`)

## Solución de problemas

| Problema | Causa probable | Solución |
|---|---|---|
| `credentials.json not found` | Falta el archivo | Copiarlo como se indica arriba |
| `Gmail auth failed` | App Password incorrecto | Verificar `.env` → `GMAIL_APP_PASSWORD` |
| Dashboard no carga datos | Sheet no es público | Compartir como "Cualquier persona con enlace" |
| Sitio no scrapea | Sitio cambió su HTML | Revisar el log y ajustar selector en `scrapers.py` |
| `token.json` expirado | Token vencido | Borrar `token.json` y re-autenticar con `python3 monitor.py` |
```

- [ ] **Step 2: Commit README**

```bash
git add README.md
git commit -m "docs: full deployment and usage instructions"
```

---

## Task 10: Push to GitHub & Enable GitHub Pages

- [ ] **Step 1: Connect to your existing GitHub repo**

```bash
git remote add origin https://github.com/TU_USUARIO/parceria-grants-dashboard.git
git branch -M main
git push -u origin main
```

- [ ] **Step 2: Enable GitHub Pages**

Go to: `https://github.com/TU_USUARIO/parceria-grants-dashboard/settings/pages`

- Source: Deploy from a branch
- Branch: `main` / folder: `/dashboard`
- Save

Expected: within ~2 minutes, your dashboard is live at `https://TU_USUARIO.github.io/parceria-grants-dashboard/`

- [ ] **Step 3: Update dashboard URL in `email_notify.py`**

In `email_notify.py`, line:
```python
dashboard_url = "https://<tu-usuario>.github.io/parceria-grants-dashboard/"
```
Replace `<tu-usuario>` with your actual GitHub username. Commit and push.

---

## Self-Review: Spec Coverage Check

| Requirement | Task |
|---|---|
| OAuth 2.0 con credentials.json | Task 2 |
| Leer Sheet para saber qué ya existe | Task 2 (`get_existing_urls`) |
| Scraping de 9 sitios con error handling | Task 3 |
| Filtrado por keywords | Task 3 (`matches_keywords`) |
| Solo agregar entradas NUEVAS | Task 6 (`monitor.py` dedup logic) |
| 7 columnas nuevas si no existen | Task 2 (`ensure_columns`) |
| Email con nuevas oportunidades | Task 5 |
| Email con deadlines próximos (30 días) | Task 5 (`urgent_section`) |
| Gmail App Password (no OAuth) | Task 5 (SMTP_SSL) |
| Dashboard con tarjetas visuales | Task 7 |
| Colores de Parcería | Task 7 (CSS variables) |
| Semáforo de urgencia (<14 / <30 / 30+) | Task 4 + Task 7 |
| Filtros por Estado, Entidad_Parceria, Urgencia | Task 7 |
| Búsqueda por nombre/entidad | Task 7 |
| Responsive (móvil) | Task 7 |
| Abrir link en nueva pestaña | Task 7 |
| Cron job lunes 8am launchd | Task 8 |
| Logs en `/logs/` | Task 6 |
| Instrucciones de deploy | Task 9 + Task 10 |
| Errores manejados gracefully | Task 3 (`safe_get`) |
| Dashboard funciona con campos vacíos | Task 7 (`f()` helper) |
