#!/bin/bash
cd "/Users/miyukikasahara/documents/Parceria Dashboard"
source .venv/bin/activate
echo "Iniciando servidor Parcería en puerto 5001..."
python3 app.py &
echo "Servidor iniciado en http://localhost:5001"
echo "Para detenerlo: kill \$(lsof -ti:5001)"
