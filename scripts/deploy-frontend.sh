#!/bin/bash
# ================================================================
# deploy-frontend.sh
# Déploie les fichiers frontend sur la VM Nginx
# Usage : sudo bash deploy-frontend.sh <chemin_source>
# ================================================================
set -e

SOURCE_DIR="${1:-/tmp/frontend}"
WEB_DIR="/var/www/html"
BACKUP_BASE="/var/backups/frontend"
BACKUP_DIR="$BACKUP_BASE/$(date +%Y%m%d_%H%M%S)"
HEALTH_URL="http://localhost:80/"
HEALTH_RETRIES=5
HEALTH_WAIT=3

echo "========================================"
echo " DEPLOY FRONTEND - $(date)"
echo " Source : $SOURCE_DIR"
echo " Cible  : $WEB_DIR"
echo "========================================"

# 1. Backup
echo "[1/5] Backup..."
mkdir -p "$BACKUP_DIR"
[ -d "$WEB_DIR" ] && [ "$(ls -A $WEB_DIR)" ] && cp -r "$WEB_DIR/." "$BACKUP_DIR/" || echo "Rien à sauvegarder."

# 2. Déploiement fichiers
echo "[2/5] Déploiement fichiers..."
mkdir -p "$WEB_DIR"
rsync -av --delete "$SOURCE_DIR/" "$WEB_DIR/"

# 3. Permissions
echo "[3/5] Permissions..."
chown -R www-data:www-data "$WEB_DIR"
chmod -R 755 "$WEB_DIR"

# 4. Test config + reload Nginx
echo "[4/5] Reload Nginx..."
nginx -t
systemctl reload nginx

# 5. Health check + rollback
echo "[5/5] Health check $HEALTH_URL..."
SUCCESS=false
for i in $(seq 1 $HEALTH_RETRIES); do
  echo "  Tentative $i/$HEALTH_RETRIES..."
  if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
    SUCCESS=true; break
  fi
  sleep $HEALTH_WAIT
done

if [ "$SUCCESS" = true ]; then
  echo "✅ Frontend déployé avec succès sur $(hostname)!"
  find "$BACKUP_BASE" -maxdepth 1 -type d -mtime +7 -exec rm -rf {} + 2>/dev/null || true
else
  echo "❌ Health check échoué! Rollback..."
  rsync -av --delete "$BACKUP_DIR/" "$WEB_DIR/"
  chown -R www-data:www-data "$WEB_DIR"
  systemctl reload nginx
  echo "Rollback depuis $BACKUP_DIR"
  exit 1
fi
