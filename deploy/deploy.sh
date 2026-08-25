#!/usr/bin/env bash
# Script de despliegue — se ejecuta EN LA VPS, dentro de /var/www/tutor_ia.
# Uso: ./deploy/deploy.sh
set -euo pipefail

APP_DIR="/var/www/tutor_ia"
cd "$APP_DIR"

echo "==> git pull"
git pull

echo "==> activando entorno virtual"
source venv/bin/activate

echo "==> instalando dependencias"
pip install -r requirements.txt -q

echo "==> migraciones"
python manage.py migrate --noinput

echo "==> estáticos"
python manage.py collectstatic --noinput

echo "==> reiniciando servicio"
sudo systemctl restart tutor_ia

echo "==> listo"
sudo systemctl status tutor_ia --no-pager -l | head -n 10
