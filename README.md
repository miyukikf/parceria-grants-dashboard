# Parcería Grants Monitor

Sistema automático de monitoreo de oportunidades de fondos para Parcería (República Dominicana).

Corre cada lunes a las 8:00am, escanea 9 sitios de financiamiento, filtra por relevancia, agrega entradas nuevas al Google Sheet y envía un resumen por email.

## Estructura de archivos

```
Parceria Dashboard/
  monitor.py              ← Script principal (scraping + Sheet + email)
  scrapers.py             ← Parsers por sitio web + filtro de keywords
  sheets.py               ← Integración Google Sheets (OAuth 2.0)
  email_notify.py         ← Envío de email vía Gmail App Password
  dashboard/
    index.html            ← Dashboard estático (GitHub Pages)
  credentials.json        ← Poner aquí manualmente (NO commitear)
  token.json              ← Se genera automáticamente (NO commitear)
  .env                    ← Variables de entorno (NO commitear)
  .env.example            ← Plantilla segura para compartir
  com.parceria.monitor.plist  ← Cron job (launchd, macOS)
  logs/                   ← Logs automáticos con timestamp
  requirements.txt        ← Dependencias Python
```

## Requisitos previos

- Python 3.9+
- `credentials.json` de Google Cloud Console (OAuth 2.0, tipo Desktop app)
- Gmail con verificación en 2 pasos + App Password
- Google Sheet compartido como "Cualquier persona con el enlace" puede ver

## Setup inicial (primera vez)

### 1. Copiar `credentials.json`

Descarga el archivo de [Google Cloud Console](https://console.cloud.google.com) y cópialo aquí:

```bash
cp ~/Downloads/credentials.json "/Users/miyukikasahara/documents/Parceria Dashboard/credentials.json"
```

### 2. Configurar `.env`

```bash
cd "/Users/miyukikasahara/documents/Parceria Dashboard"
cp .env.example .env
```

Edita `.env` con tus valores reales:

```
GMAIL_USER=mkasahara@somosparceria.com
GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
NOTIFY_TO=mkasahara@somosparceria.com
SHEET_ID=1dU2Tep3gakBNDPR5zRJdth_MDb5X_TVUratBgmQESHg
```

> **¿Cómo conseguir un App Password?**
> Gmail → Cuenta → Seguridad → Verificación en 2 pasos → Contraseñas de aplicación → Nueva → "Parceria Monitor"

### 3. Instalar dependencias

```bash
cd "/Users/miyukikasahara/documents/Parceria Dashboard"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. Primer run manual (abre el navegador para autorizar)

```bash
source .venv/bin/activate
python3 monitor.py
```

La primera vez se abrirá el navegador para autorizar el acceso a Google Sheets. Acepta con tu cuenta de Google. Se crea `token.json` automáticamente — las próximas ejecuciones no requieren el navegador.

## Activar el cron job (launchd, macOS)

```bash
cp "/Users/miyukikasahara/documents/Parceria Dashboard/com.parceria.monitor.plist" \
   ~/Library/LaunchAgents/

launchctl load ~/Library/LaunchAgents/com.parceria.monitor.plist

# Verificar que está activo
launchctl list | grep parceria
```

Corre automáticamente **cada lunes a las 8:00am**.

**Para desactivarlo:**
```bash
launchctl unload ~/Library/LaunchAgents/com.parceria.monitor.plist
```

**Para correrlo manualmente ahora (sin abrir terminal):**
```bash
launchctl start com.parceria.monitor
```

**Ver los logs:**
```bash
tail -f "/Users/miyukikasahara/documents/Parceria Dashboard/logs/launchd_stdout.log"
```

## Dashboard en GitHub Pages

1. Sube el repositorio a GitHub → `miyukikf/parceria-grants-dashboard`
2. Ve a **Settings → Pages → Source:** branch `main`, carpeta `/dashboard`
3. En ~2 minutos el dashboard estará en:
   **https://miyukikf.github.io/parceria-grants-dashboard/**

> El dashboard requiere que el Sheet esté compartido como "Cualquier persona con el enlace puede ver".

## Sitios monitoreados

| Sitio | Entidad |
|-------|---------|
| carib-export.com/opportunities/ | Caribbean Export |
| eulacdigitalaccelerator.com | EU-LAC Digital Accelerator |
| bidlab.org/en/calls | BID Lab |
| programafrida.net/convocatorias/ | Programa FRIDA |
| cartierwomensinitiative.com/awards | Cartier Women's Initiative |
| gdlab.iadb.org/en/call | GD Lab IADB |
| caribank.org | Caribbean Development Bank |
| do.undp.org | UNDP República Dominicana |
| goethe.de/en/kul/foe/int.html | Goethe Institut |

## Keywords de filtrado

género, equidad, mujeres, youth, juventud, workforce, digital, inclusión, ESG, sostenibilidad, impacto social, caribe, caribbean, república dominicana, dominican republic, LAC, women, gender, equity

## Columnas del Google Sheet

**Existentes** (no se modifican): `Nombre | Entidad | Monto | Fecha_Cierre | URL | Descripcion`

**Agregadas automáticamente si no existen:**

| Columna | Descripción | Default |
|---------|-------------|---------|
| Entidad_Parceria | Parcería / Fundación / Gina / Todos | Todos |
| Estado | Estado de la oportunidad | Identificado |
| Urgencia | Alta / Media / Baja según fecha de cierre | Calculado |
| Consorcio_Requerido | Sí / No / Por confirmar | Por confirmar |
| Socio_Consorcio | Nombre del socio si aplica | — |
| Fecha_Verificada | Fecha en que se encontró | Hoy |
| Link_Propuesta | URL de la propuesta enviada | — |

## Lógica de urgencia

| Urgencia | Condición |
|----------|-----------|
| 🔴 Alta | Cierra en menos de 14 días |
| 🟡 Media | Cierra en menos de 30 días |
| 🟢 Baja | Más de 30 días o sin fecha |

## Solución de problemas

| Problema | Causa probable | Solución |
|----------|---------------|---------|
| `credentials.json not found` | Falta el archivo | Copiar como se indica en Setup |
| `Gmail auth failed` | App Password incorrecto | Verificar `.env → GMAIL_APP_PASSWORD` |
| Dashboard muestra "Error al cargar datos" | Sheet no es público | Share → "Cualquier persona con el enlace" → Lector |
| Sitio no scrapea | El sitio cambió su HTML | Revisar el log y ajustar el selector CSS en `scrapers.py` |
| `token.json` expirado | Token OAuth vencido | Borrar `token.json` y correr `python3 monitor.py` nuevamente |
| launchd no corre | plist no cargado | Verificar con `launchctl list \| grep parceria` |
```
