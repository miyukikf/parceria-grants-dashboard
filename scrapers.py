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
    """https://bidlab.org/en/calls-for-proposals"""
    url = "https://bidlab.org/en/calls-for-proposals"
    soup = safe_get(session, url)
    if not soup:
        return []

    results = []
    for item in soup.select(".call-card, article, .listing-item, .challenge-item"):
        title_el = item.select_one("h2, h3, h4, .title, a")
        if not title_el or len(title_el.get_text(strip=True)) < 8:
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

    if not results:
        results.append(make_opp(
            "BID Lab – Convocatorias de Innovación",
            "BID Lab", url,
            descripcion="Verificar convocatorias activas en el sitio de BID Lab.",
            fuente="bidlab.org"
        ))
    logger.info(f"bidlab.org: {len(results)} matching opportunities")
    return results


def scrape_frida(session: requests.Session) -> list:
    """https://programafrida.net"""
    url = "https://programafrida.net"
    bases_url = "https://programafrida.net/wp-content/uploads/2025/05/Bases-FRIDA-2025_ES-.pdf"
    soup = safe_get(session, url)
    if not soup:
        return []

    results = []
    # Look for any convocatoria or call items in the page
    for item in soup.select("article, .convocatoria, .post, .entry, li.item"):
        title_el = item.select_one("h2, h3, .entry-title, a")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if len(title) < 8:
            continue
        link_el = item.select_one("a[href]")
        link = link_el["href"] if link_el else url
        if not link.startswith("http"):
            link = "https://programafrida.net" + link
        desc = item.get_text(" ", strip=True)[:300]
        if matches_keywords(title + " " + desc):
            results.append(make_opp(title, "Programa FRIDA", link,
                                    descripcion=desc, fuente="programafrida.net"))

    if not results:
        results.append(make_opp(
            "Programa FRIDA 2025 – Convocatoria Abierta",
            "Programa FRIDA", bases_url,
            descripcion=(
                "FRIDA apoya proyectos de internet en América Latina y el Caribe. "
                "Revisar bases y convocatoria activa en el sitio."
            ),
            fuente="programafrida.net"
        ))
    logger.info(f"programafrida.net: {len(results)} matching opportunities")
    return results


def scrape_cartier(session: requests.Session) -> list:
    """https://www.cartierwomensinitiative.com/awards"""
    url = "https://www.cartierwomensinitiative.com/awards"
    soup = safe_get(session, url)
    if not soup:
        return []

    results = []
    seen_titles = set()

    # Target section-level h2 headings (e.g. "Regional Awards", "Thematic Award")
    # and card-level h3 headings (e.g. "LATIN AMERICA AND THE CARIBBEAN")
    # These live in .section-title > h2 and .cards__card h3, NOT in nav
    for title_el in soup.select(".section-title > h2, .cards__card h3, .cards__card h2"):
        title = title_el.get_text(strip=True)
        if len(title) < 8:
            continue
        if title in seen_titles:
            continue
        seen_titles.add(title)
        # Find nearest ancestor link or use page url
        link_el = title_el.find_parent("a")
        if not link_el:
            card = title_el.find_parent(class_="cards__card")
            link_el = card.select_one("a[href]") if card else None
        if link_el and link_el.get("href"):
            link = link_el["href"]
            if not link.startswith("http"):
                link = "https://www.cartierwomensinitiative.com" + link
        else:
            link = url
        desc = title_el.find_parent("section") or title_el.find_parent("div")
        desc_text = desc.get_text(" ", strip=True)[:300] if desc else title
        if matches_keywords(title + " " + desc_text + " women mujeres"):
            results.append(make_opp(title, "Cartier Women's Initiative", link,
                                    descripcion=desc_text,
                                    fuente="cartierwomensinitiative.com"))

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

    # Category/tag words that are NOT call titles — skip these
    SKIP_WORDS = {
        "gender", "diversity", "completed", "home", "videos",
        "género", "diversidad", "completado",
    }

    results = []
    # Calls are listed as <li> items containing <strong> title text
    for item in soup.select("li"):
        title_el = item.select_one("strong")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if len(title) < 8:
            continue
        if title.lower() in SKIP_WORDS:
            continue
        link_el = item.select_one("a[href]")
        link = link_el["href"] if link_el else url
        if not link.startswith("http"):
            link = "https://gdlab.iadb.org" + link
        desc = item.get_text(" ", strip=True)[:300]
        if matches_keywords(title + " " + desc):
            results.append(make_opp(title, "GD Lab IADB", link,
                                    descripcion=desc, fuente="gdlab.iadb.org"))

    if not results:
        results.append(make_opp(
            "GDLab – Convocatorias de Investigación sobre Género y Diversidad",
            "GD Lab IADB", url,
            descripcion="Iniciativa de Conocimiento sobre Género y Diversidad del BID.",
            fuente="gdlab.iadb.org"
        ))
    logger.info(f"gdlab.iadb.org: {len(results)} matching opportunities")
    return results


def scrape_caribank(session: requests.Session) -> list:
    """https://www.caribank.org/our-work/programmes/cultural-and-creative-industries-innovation-fund"""
    url = "https://www.caribank.org/our-work/programmes/cultural-and-creative-industries-innovation-fund"
    soup = safe_get(session, url)
    if not soup:
        return []

    results = []
    # The main h1 on this page is the programme title; skip nav or short strings
    title = "Cultural and Creative Industries Innovation Fund"
    for title_el in soup.select("h1"):
        candidate = title_el.get_text(strip=True)
        if len(candidate) >= 15 and "navigation" not in candidate.lower():
            title = candidate
            break

    desc_el = soup.select_one(".field-body, .page-description, main p, article p, p")
    desc = desc_el.get_text(" ", strip=True)[:300] if desc_el else ""
    if matches_keywords(title + " " + desc + " caribbean cultural creative"):
        results.append(make_opp(title, "Caribbean Development Bank", url,
                                descripcion=desc, fuente="caribank.org"))

    if not results:
        results.append(make_opp(
            "Cultural and Creative Industries Innovation Fund (CIIF)",
            "Caribbean Development Bank", url,
            descripcion="Fondo de innovación para industrias culturales y creativas del Caribe.",
            fuente="caribank.org"
        ))
    logger.info(f"caribank.org: {len(results)} matching opportunities")
    return results


def scrape_undp_do(session: requests.Session) -> list:
    """https://procurement-notices.undp.org"""
    url = "https://procurement-notices.undp.org"
    soup = safe_get(session, url)
    if not soup:
        return []

    results = []
    # Each notice is an <a> element; first span inside contains the title
    for item in soup.select("a[href*='view_negotiation.cfm'], a[href*='view_notice.cfm']"):
        spans = item.select("span")
        if not spans:
            continue
        title = spans[0].get_text(strip=True)
        if len(title) < 8:
            continue
        href = item.get("href", "")
        if href.startswith("http"):
            link = href
        else:
            link = url.rstrip("/") + "/" + href.lstrip("/")
        # Deadline is typically the 5th span (index 4)
        deadline = spans[4].get_text(strip=True) if len(spans) > 4 else ""
        desc = item.get_text(" ", strip=True)[:300]
        if matches_keywords(title + " " + desc):
            results.append(make_opp(title, "UNDP", link,
                                    fecha_cierre=deadline, descripcion=desc,
                                    fuente="procurement-notices.undp.org"))

    if not results:
        results.append(make_opp(
            "UNDP Procurement Notices – Oportunidades de Financiamiento",
            "UNDP", url,
            descripcion="Verificar avisos de adquisición y convocatorias activas.",
            fuente="procurement-notices.undp.org"
        ))
    logger.info(f"procurement-notices.undp.org: {len(results)} matching opportunities")
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
