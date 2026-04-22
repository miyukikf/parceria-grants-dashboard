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
