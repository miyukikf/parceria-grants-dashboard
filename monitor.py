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

    SHEET_ID   = os.environ.get("SHEET_ID", "1dU2Tep3gakBNDPR5zRJdth_MDb5X_TVUratBgmQESHg")
    GMAIL_USER = os.environ.get("GMAIL_USER", "")
    GMAIL_PASS = os.environ.get("GMAIL_APP_PASSWORD", "")
    NOTIFY_TO  = os.environ.get("NOTIFY_TO", GMAIL_USER)

    logger.info("=== Parcería Grants Monitor starting ===")

    # 1. Authenticate and open sheet
    logger.info("Authenticating with Google Sheets...")
    client = get_authenticated_client()
    ws = open_sheet(client, SHEET_ID)
    col_map = ensure_columns(ws)
    logger.info(f"Sheet opened. Columns: {list(col_map.keys())}")

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
