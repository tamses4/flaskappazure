#!/bin/bash
# ================================================================
# install-agent.sh
# Installe l'agent Azure DevOps sur une VM Linux
# Usage : sudo bash install-agent.sh <AGENT_NAME> <POOL_NAME> <ORG_URL> <PAT_TOKEN>
#
# Exemples :
#   sudo bash install-agent.sh backend-1 vm-backend https://dev.azure.com/MON_ORG TOKEN
#   sudo bash install-agent.sh backend-2 vm-backend https://dev.azure.com/MON_ORG TOKEN
#   sudo bash install-agent.sh frontend-1 vm-frontend https://dev.azure.com/MON_ORG TOKEN
# ================================================================
set -e

AGENT_NAME="${1:?Argument manquant: AGENT_NAME}"
POOL_NAME="${2:?Argument manquant: POOL_NAME}"
ORG_URL="${3:?Argument manquant: ORG_URL}"
PAT_TOKEN="${4:?Argument manquant: PAT_TOKEN}"

AGENT_VERSION="3.236.1"
AGENT_DIR="/opt/azure-agent"
AGENT_USER="azureagent"

echo "========================================"
echo " INSTALLATION AGENT AZURE DEVOPS"
echo " Agent : $AGENT_NAME | Pool : $POOL_NAME"
echo "========================================"

# 1. Dépendances
echo "[1/5] Installation dépendances..."
apt-get update -qq
apt-get install -y curl wget rsync libssl-dev libicu-dev

# 2. Créer utilisateur agent
echo "[2/5] Création utilisateur $AGENT_USER..."
id "$AGENT_USER" &>/dev/null || useradd -m -s /bin/bash "$AGENT_USER"
# Autoriser sudo sans mot de passe pour les scripts de déploiement
echo "$AGENT_USER ALL=(ALL) NOPASSWD: /bin/bash /opt/monapp/deploy-*.sh, /bin/bash */scripts/deploy-*.sh, /bin/systemctl" \
  > /etc/sudoers.d/azure-agent
chmod 440 /etc/sudoers.d/azure-agent

# 3. Téléchargement agent
echo "[3/5] Téléchargement agent v$AGENT_VERSION..."
mkdir -p "$AGENT_DIR"
cd "$AGENT_DIR"
if [ ! -f "run.sh" ]; then
  wget -q "https://vstsagentpackage.azureedge.net/agent/${AGENT_VERSION}/vsts-agent-linux-x64-${AGENT_VERSION}.tar.gz"
  tar -xzf "vsts-agent-linux-x64-${AGENT_VERSION}.tar.gz"
  rm -f "vsts-agent-linux-x64-${AGENT_VERSION}.tar.gz"
fi
chown -R "$AGENT_USER:$AGENT_USER" "$AGENT_DIR"

# 4. Configuration
echo "[4/5] Configuration de l'agent..."
sudo -u "$AGENT_USER" "$AGENT_DIR/config.sh" \
  --unattended \
  --url "$ORG_URL" \
  --auth pat \
  --token "$PAT_TOKEN" \
  --pool "$POOL_NAME" \
  --agent "$AGENT_NAME" \
  --replace \
  --acceptTeeEula

# 5. Installation service
echo "[5/5] Installation comme service systemd..."
"$AGENT_DIR/svc.sh" install "$AGENT_USER"
"$AGENT_DIR/svc.sh" start

echo ""
echo "✅ Agent '$AGENT_NAME' installé et démarré dans le pool '$POOL_NAME'!"
echo "   Vérifier sur : $ORG_URL/_settings/agentpools"
