# sheets.py
import logging
from pathlib import Path
import gspread
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

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


def get_existing_keys(ws: gspread.Worksheet) -> tuple[set, set]:
    """
    Return (existing_urls, existing_name_entity_pairs) for deduplication.
    name_entity key = normalized "nombre|entidad" string.
    """
    records = ws.get_all_records()
    urls = set()
    name_entity = set()
    for row in records:
        url = row.get("Link") or row.get("link") or row.get("URL") or row.get("url") or ""
        if url:
            urls.add(url.strip())
        nombre = str(row.get("Nombre de la oportunidad") or row.get("Nombre") or "").strip().lower()
        entidad = str(row.get("Entidad") or "").strip().lower()
        if nombre:
            name_entity.add(f"{nombre}|{entidad}")
    return urls, name_entity


def get_existing_urls(ws: gspread.Worksheet) -> set:
    """Backwards-compatible: return just the URL set."""
    urls, _ = get_existing_keys(ws)
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
        "Nombre de la oportunidad": opp.get("nombre", ""),
        "Entidad": opp.get("entidad", ""),
        "Cantidad de fondos": opp.get("monto", ""),
        "Fecha de cierre": opp.get("fecha_cierre", ""),
        "Link": opp.get("url", ""),
        "Requisitos": opp.get("descripcion", ""),
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
