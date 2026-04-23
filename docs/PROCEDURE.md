# Procédure de mise en place CI/CD — Azure Repos + Pipeline

## Prérequis
- Architecture Azure existante (VMs, Load Balancers, Bastion, NAT Gateway)
- Accès Azure DevOps (organisation + projet créés)
- Azure CLI installé sur ta machine locale
- Clé SSH générée (`~/.ssh/id_rsa` + `~/.ssh/id_rsa.pub`)

---

## ÉTAPE 1 — Préparer Azure DevOps

### 1.1 Créer les Agent Pools
Dans Azure DevOps → **Project Settings → Agent Pools → New agent pool** :
- Créer le pool : `vm-backend`
- Créer le pool : `vm-frontend`

### 1.2 Générer un PAT Token
Dans Azure DevOps → **User Settings → Personal Access Tokens → New Token** :
- Nom : `agent-install-token`
- Scope : **Agent Pools (Read & Manage)**
- Durée : 90 jours (renouveler avant expiration)
- **⚠️ Copier le token immédiatement, il ne sera plus visible après**

---

## ÉTAPE 2 — Installer l'agent sur chaque VM

### Connexion aux VMs via Bastion
```bash
# Depuis n'importe quelle machine avec Azure CLI installé
az login

# Connexion VM Frontend
az network bastion ssh \
  --name bastion-monapp \
  --resource-group rg-monapp \
  --target-resource-id /subscriptions/{SUB_ID}/resourceGroups/rg-monapp/providers/Microsoft.Compute/virtualMachines/vm-frontend \
  --auth-type ssh-key \
  --username azureuser \
  --ssh-key ~/.ssh/id_rsa

# Connexion VM Backend-1
az network bastion ssh \
  --name bastion-monapp \
  --resource-group rg-monapp \
  --target-resource-id /subscriptions/{SUB_ID}/resourceGroups/rg-monapp/providers/Microsoft.Compute/virtualMachines/vm-backend-1 \
  --auth-type ssh-key \
  --username azureuser \
  --ssh-key ~/.ssh/id_rsa
```

### Installation de l'agent (à répéter sur chaque VM)

**Sur vm-backend-1 :**
```bash
# Copier le script sur la VM (depuis ta machine locale)
az network bastion tunnel \
  --name bastion-monapp \
  --resource-group rg-monapp \
  --target-resource-id /subscriptions/{SUB_ID}/.../vm-backend-1 \
  --resource-port 22 \
  --port 2222 &

scp -P 2222 scripts/install-agent.sh azureuser@127.0.0.1:~

# Puis dans la session SSH sur la VM :
sudo bash install-agent.sh \
  "backend-1" \
  "vm-backend" \
  "https://dev.azure.com/TON_ORGANISATION" \
  "TON_PAT_TOKEN"
```

**Sur vm-backend-2 :**
```bash
sudo bash install-agent.sh \
  "backend-2" \
  "vm-backend" \
  "https://dev.azure.com/TON_ORGANISATION" \
  "TON_PAT_TOKEN"
```

**Sur vm-frontend :**
```bash
sudo bash install-agent.sh \
  "frontend-1" \
  "vm-frontend" \
  "https://dev.azure.com/TON_ORGANISATION" \
  "TON_PAT_TOKEN"
```

### Vérification
Dans Azure DevOps → **Project Settings → Agent Pools** :
- `vm-backend` → doit afficher `backend-1` ✅ et `backend-2` ✅
- `vm-frontend` → doit afficher `frontend-1` ✅

---

## ÉTAPE 3 — Configurer Azure Repos

### 3.1 Cloner le dépôt
```bash
git clone https://dev.azure.com/TON_ORGANISATION/TON_PROJET/_git/TON_REPO
cd TON_REPO
```

### 3.2 Copier les fichiers du projet
```
Copier dans le dépôt :
├── azure-pipelines.yml         → à la racine
├── scripts/
│   ├── deploy-backend.sh
│   ├── deploy-frontend.sh
│   └── nginx-frontend.conf     (référence uniquement)
├── frontend/
│   ├── index.html
│   ├── css/
│   └── js/
└── backend/
    └── config/
        └── app.conf
```

### 3.3 Premier push
```bash
git add .
git commit -m "feat: setup CI/CD pipeline"
git push origin main
```

---

## ÉTAPE 4 — Créer le Pipeline dans Azure DevOps

1. Azure DevOps → **Pipelines → New Pipeline**
2. Sélectionner **Azure Repos Git**
3. Sélectionner ton dépôt
4. Choisir **Existing Azure Pipelines YAML file**
5. Sélectionner `/azure-pipelines.yml`
6. Cliquer **Save and Run**

---

## ÉTAPE 5 — Configurer Nginx sur la VM Frontend

Se connecter à la VM frontend et appliquer la config :
```bash
# Copier la config Nginx
sudo cp /var/www/html/../scripts/nginx-frontend.conf \
  /etc/nginx/sites-available/monapp

# ⚠️ Modifier l'IP du LB interne si différente de 10.0.2.10
sudo nano /etc/nginx/sites-available/monapp

# Activer le site
sudo ln -sf /etc/nginx/sites-available/monapp \
  /etc/nginx/sites-enabled/monapp

# Désactiver le site par défaut
sudo rm -f /etc/nginx/sites-enabled/default

# Tester et recharger
sudo nginx -t && sudo systemctl reload nginx
```

---

## ÉTAPE 6 — Workflow quotidien

### Déployer du code
```bash
# Modifier tes fichiers frontend ou backend
vim frontend/js/app.js
vim backend/app.py

# Committer et pousser → le pipeline se déclenche automatiquement
git add .
git commit -m "fix: correction bug login"
git push origin main
```

### Déploiement sélectif par message de commit (optionnel)
```bash
git commit -m "[backend] mise à jour API"    # → déclenche seulement backend
git commit -m "[frontend] nouveau design"    # → déclenche seulement frontend
git commit -m "[all] release v2.0"           # → déclenche tout
```

### Se connecter à une VM depuis n'importe où
```bash
az login   # si pas encore connecté

az network bastion ssh \
  --name bastion-monapp \
  --resource-group rg-monapp \
  --target-resource-id /subscriptions/{SUB_ID}/.../vm-backend-1 \
  --auth-type ssh-key \
  --username azureuser \
  --ssh-key ~/.ssh/id_rsa
```

---

## Rollback manuel

```bash
# Via git → revenir au commit précédent
git revert HEAD
git push origin main
# → Le pipeline se relance et redéploie l'ancienne version

# Ou directement sur la VM (backup automatique conservé 7 jours)
ls /var/backups/backend/
sudo rsync -av /var/backups/backend/20240101_120000/ /opt/monapp/backend/
sudo systemctl restart monapp
```

---

## Dépannage

| Problème | Solution |
|---|---|
| Agent hors ligne dans DevOps | `sudo /opt/azure-agent/svc.sh status` puis `start` |
| Health check échoue | Vérifier `journalctl -u monapp -n 50` |
| Nginx KO | `sudo nginx -t` pour voir l'erreur |
| Pipeline bloqué en attente | Vérifier que l'agent est Online dans le pool |
| SSH Bastion refusé | Vérifier que la clé publique est dans `~/.ssh/authorized_keys` sur la VM |
