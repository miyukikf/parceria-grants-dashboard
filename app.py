# app.py — Parcería Grants Monitor local API server
# Exposes POST /run-monitor and GET /health
# Run via start.sh

import subprocess
import sys
import logging
from pathlib import Path
from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Allow calls from GitHub Pages (miyukikf.github.io)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).parent
MONITOR_SCRIPT = PROJECT_DIR / "monitor.py"
PYTHON_BIN = PROJECT_DIR / ".venv" / "bin" / "python3"


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "project": "Parcería Grants Monitor"})


@app.route("/run-monitor", methods=["POST"])
def run_monitor():
    logger.info("POST /run-monitor — starting monitor.py")
    try:
        result = subprocess.run(
            [str(PYTHON_BIN), str(MONITOR_SCRIPT)],
            cwd=str(PROJECT_DIR),
            capture_output=True,
            text=True,
            timeout=300,  # 5 minutes max
        )
        if result.returncode == 0:
            # Count "Appended:" lines as a proxy for new opportunities added
            new_count = result.stdout.count("Appended:")
            logger.info(f"monitor.py finished OK — {new_count} new opportunities")
            return jsonify({
                "status": "ok",
                "message": f"Monitor ejecutado. {new_count} nueva{'s' if new_count != 1 else ''} oportunidad{'es' if new_count != 1 else ''} agregada{'s' if new_count != 1 else ''}.",
                "new_count": new_count,
            })
        else:
            logger.error(f"monitor.py failed: {result.stderr[:500]}")
            return jsonify({
                "status": "error",
                "error": f"El monitor falló. Revisa los logs en logs/.",
                "stderr": result.stderr[:500],
            }), 500
    except subprocess.TimeoutExpired:
        return jsonify({"status": "error", "error": "El monitor tardó más de 5 minutos."}), 504
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)
