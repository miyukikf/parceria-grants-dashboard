# email_notify.py
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

logger = logging.getLogger(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465


def _build_html(new_opps: list, sheet_id: str) -> str:
    """Build the HTML body for the summary email."""
    sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}"
    dashboard_url = "https://miyukikf.github.io/parceria-grants-dashboard/"

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
        <h2 style="color:#e74c3c">&#9888;&#65039; Cierran en menos de 30 días</h2>
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

    nueva_s = "s" if len(new_opps) != 1 else ""
    encontrada_s = "s" if len(new_opps) != 1 else ""
    oportunidad_es = "es" if len(new_opps) != 1 else ""

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
          {len(new_opps)} nueva{nueva_s} oportunidad{oportunidad_es} encontrada{encontrada_s}
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

    nueva_s = "s" if len(new_opps) != 1 else ""
    oportunidad_es = "es" if len(new_opps) != 1 else ""
    subject = (
        f"[Parcería] {len(new_opps)} nueva{nueva_s} "
        f"oportunidad{oportunidad_es} · "
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
