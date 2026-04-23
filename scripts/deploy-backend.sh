#!/bin/bash
# ================================================================
# deploy-backend.sh
# Déploie les fichiers backend sur la VM courante
# Usage : sudo bash deploy-backend.sh <chemin_source>
# ================================================================
set -e

SOURCE_DIR="${1:-/tmp/backend}"
APP_DIR="/opt/monapp/backend"
CONFIG_DIR="/etc/monapp"
BACKUP_BASE="/var/backups/backend"
BACKUP_DIR="$BACKUP_BASE/$(date +%Y%m%d_%H%M%S)"
SERVICE_NAME="monapp"
HEALTH_URL="http://localhost:5000/health"
HEALTH_RETRIES=10
HEALTH_WAIT=3

echo "========================================"
echo " DEPLOY BACKEND - $(date)"
echo " Source  : $SOURCE_DIR"
echo " Cible   : $APP_DIR"
echo "========================================"

# 1. Backup
echo "[1/6] Backup..."
mkdir -p "$BACKUP_DIR"
[ -d "$APP_DIR" ] && [ "$(ls -A $APP_DIR)" ] && cp -r "$APP_DIR/." "$BACKUP_DIR/" || echo "Rien à sauvegarder."

# 2. Arrêt service
echo "[2/6] Arrêt du service $SERVICE_NAME..."
systemctl stop $SERVICE_NAME || echo "Service déjà arrêté."

# 3. Déploiement fichiers
echo "[3/6] Déploiement fichiers..."
mkdir -p "$APP_DIR"
rsync -av --delete --exclude='config/' "$SOURCE_DIR/" "$APP_DIR/"

# 4. Config
echo "[4/6] Déploiement config..."
mkdir -p "$CONFIG_DIR"
if [ -f "$SOURCE_DIR/config/app.conf" ]; then
  cp "$SOURCE_DIR/config/app.conf" "$CONFIG_DIR/app.conf"
  echo "app.conf déployé."
else
  echo "Pas de config, on garde l'existante."
fi

# 5. Redémarrage
echo "[5/6] Redémarrage $SERVICE_NAME..."
systemctl start $SERVICE_NAME
sleep 3

# 6. Health check + rollback
echo "[6/6] Health check $HEALTH_URL..."
SUCCESS=false
for i in $(seq 1 $HEALTH_RETRIES); do
  echo "  Tentative $i/$HEALTH_RETRIES..."
  if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
    SUCCESS=true; break
  fi
  sleep $HEALTH_WAIT
done

if [ "$SUCCESS" = true ]; then
  echo "✅ Backend déployé avec succès sur $(hostname)!"
  find "$BACKUP_BASE" -maxdepth 1 -type d -mtime +7 -exec rm -rf {} + 2>/dev/null || true
else
  echo "❌ Health check échoué! Rollback..."
  systemctl stop $SERVICE_NAME
  [ -d "$BACKUP_DIR" ] && [ "$(ls -A $BACKUP_DIR)" ] && rsync -av --delete "$BACKUP_DIR/" "$APP_DIR/"
  systemctl start $SERVICE_NAME
  echo "Rollback depuis $BACKUP_DIR"
  exit 1
fi
