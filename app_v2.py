"""
app.py — Backend Flask v2 — Maison Luxe
VM Flask : 10.1.1.4:5000 (VNET-APP)

Changements v2 :
  - Azure Table Storage → Azure Database for PostgreSQL
  - Images URL Unsplash → Azure Blob Storage
  - Route POST /api/upload pour uploader les images
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from azure.storage.blob import BlobServiceClient, ContentSettings
import psycopg2
import psycopg2.extras
import os, uuid, hashlib, hmac, base64, json
from datetime import datetime, timezone

app = Flask(__name__)
CORS(app)

# ─── CONFIG ──────────────────────────────────────────────────────────────────
DB_HOST     = os.environ.get("DB_HOST", "")        # ex: monserveur.postgres.database.azure.com
DB_NAME     = os.environ.get("DB_NAME", "maisonluxe")
DB_USER     = os.environ.get("DB_USER", "")        # ex: adminuser@monserveur
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_PORT     = os.environ.get("DB_PORT", "5432")

BLOB_CONN_STR   = os.environ.get("AZURE_BLOB_CONNECTION_STRING", "")
BLOB_CONTAINER  = os.environ.get("BLOB_CONTAINER", "images")

ADMIN_EMAIL    = os.environ.get("ADMIN_EMAIL", "admin@luxe.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin2025")
SECRET_KEY     = os.environ.get("SECRET_KEY", "changez-cette-cle")

# ─── CONNEXION POSTGRESQL ────────────────────────────────────────────────────
def get_db():
    return psycopg2.connect(
        host=DB_HOST,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        port=DB_PORT,
        sslmode="require",  # Obligatoire sur Azure PostgreSQL
        cursor_factory=psycopg2.extras.RealDictCursor
    )

# ─── INIT TABLES SQL ─────────────────────────────────────────────────────────
def init_db():
    """Crée les tables si elles n'existent pas et insère les produits par défaut."""
    conn = get_db()
    cur  = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id          VARCHAR(50) PRIMARY KEY,
            name        VARCHAR(200) NOT NULL,
            category    VARCHAR(100),
            price       NUMERIC(10,2),
            badge       VARCHAR(50),
            description TEXT,
            image_url   TEXT,
            created_at  TIMESTAMP DEFAULT NOW()
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name        VARCHAR(200) NOT NULL,
            email       VARCHAR(200) UNIQUE NOT NULL,
            password    VARCHAR(256) NOT NULL,
            status      VARCHAR(20) DEFAULT 'new',
            orders      INTEGER DEFAULT 0,
            created_at  TIMESTAMP DEFAULT NOW()
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id     UUID REFERENCES users(id),
            items       JSONB,
            total       NUMERIC(10,2),
            status      VARCHAR(20) DEFAULT 'pending',
            created_at  TIMESTAMP DEFAULT NOW()
        );
    """)

    # Produits par défaut (insérés seulement si la table est vide)
    cur.execute("SELECT COUNT(*) as cnt FROM products;")
    count = cur.fetchone()["cnt"]
    if count == 0:
        default_products = [
            ("p1",  "Robe Élysée",         "Robes",        480.00, "Nouveau",     "Robe en soie naturelle, coupe asymétrique, col bénitier.",           ""),
            ("p2",  "Manteau Rivoli",       "Manteaux",     890.00, "",            "Manteau en laine mérinos double face, doublure en soie.",            ""),
            ("p3",  "Veste Marais",         "Vestes",       640.00, "Exclusif",    "Veste structurée en tweed de laine, boutons dorés.",                 ""),
            ("p4",  "Jupe Vendôme",         "Jupes",        320.00, "",            "Jupe midi en crêpe de soie, taille haute, coupe évasée.",            ""),
            ("p5",  "Chemise Opéra",        "Tops",         265.00, "",            "Chemise en popeline de coton égyptien, col classique.",              ""),
            ("p6",  "Robe Tuileries",       "Robes",        560.00, "",            "Robe longue en mousseline de soie, imprimé floral exclusif.",        ""),
            ("p7",  "Blazer Saint-Honoré",  "Vestes",       720.00, "Best-seller", "Blazer ajusté en laine vierge, passepoil contrasté.",               ""),
            ("p8",  "Pantalon Concorde",    "Pantalons",    390.00, "",            "Pantalon taille haute en crêpe texturé, coupe palazzo.",             ""),
            ("p9",  "Robe Monaco",          "Robes",        520.00, "Nouveau",     "Robe cocktail en dentelle de Calais, décolleté V, doublure soie.",   ""),
            ("p10", "Sac Faubourg",         "Accessoires", 1250.00, "Exclusif",    "Sac à main en cuir grainé, fermeture dorée, bandoulière amovible.", ""),
            ("p11", "Écharpe Cashmere",     "Accessoires",  280.00, "",            "Écharpe en cachemire pur, 200x70cm, teinture naturelle.",            ""),
            ("p12", "Combinaison Palais",   "Combinaisons", 610.00, "Best-seller", "Combinaison large en crêpe satiné, ceinture tissée assortie.",       ""),
            ("p13", "Manteau Biarritz",     "Manteaux",    1100.00, "",            "Manteau oversize en alpaga et laine, col châle, poches plaquées.",   ""),
            ("p14", "Robe Deauville",       "Robes",        740.00, "Nouveau",     "Robe longue en lin brodé, manches ballon, ceinture dorée.",          ""),
        ]
        cur.executemany("""
            INSERT INTO products (id, name, category, price, badge, description, image_url)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING;
        """, default_products)
        print(f"[init] {len(default_products)} produits insérés.")

    conn.commit()
    cur.close()
    conn.close()
    print("[init] Base PostgreSQL initialisée.")

# ─── AZURE BLOB STORAGE ───────────────────────────────────────────────────────
def get_blob_client():
    return BlobServiceClient.from_connection_string(BLOB_CONN_STR)

def init_blob_container():
    """Crée le container d'images s'il n'existe pas."""
    try:
        client = get_blob_client()
        container = client.get_container_client(BLOB_CONTAINER)
        try:
            container.create_container(public_access="blob")
            print(f"[init] Container '{BLOB_CONTAINER}' créé.")
        except Exception:
            print(f"[init] Container '{BLOB_CONTAINER}' déjà existant.")
    except Exception as e:
        print(f"[init] Erreur Blob Storage : {e}")

# ─── UTILITAIRES AUTH ─────────────────────────────────────────────────────────
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def make_token(user_id, role="user"):
    payload = json.dumps({"id": str(user_id), "role": role, "ts": datetime.now().isoformat()})
    sig = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return base64.b64encode(f"{payload}|{sig}".encode()).decode()

def verify_token(token_str):
    try:
        decoded = base64.b64decode(token_str.encode()).decode()
        payload_str, sig = decoded.rsplit("|", 1)
        expected = hmac.new(SECRET_KEY.encode(), payload_str.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        return json.loads(payload_str)
    except Exception:
        return None

def get_token_payload():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    return verify_token(auth[7:])

def require_admin():
    p = get_token_payload()
    return p if p and p.get("role") == "admin" else None

# ══════════════════════════════════════════════════════════════════════════════
# ROUTES PRODUITS
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/products", methods=["GET"])
def get_products():
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("SELECT * FROM products ORDER BY created_at DESC;")
        rows = cur.fetchall()
        cur.close(); conn.close()

        products = []
        for r in rows:
            products.append({
                "id":          r["id"],
                "name":        r["name"],
                "category":    r["category"] or "",
                "price":       str(r["price"]),
                "badge":       r["badge"] or "",
                "description": r["description"] or "",
                "imageUrl":    r["image_url"] or "",
            })

        limit = request.args.get("limit")
        if limit:
            products = products[:int(limit)]

        return jsonify({"products": products, "total": len(products)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/products", methods=["POST"])
def add_product():
    if not require_admin():
        return jsonify({"error": "Accès refusé"}), 403
    data = request.get_json()
    pid  = data.get("id") or "p-" + str(uuid.uuid4())[:8]
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("""
            INSERT INTO products (id, name, category, price, badge, description, image_url)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                name=EXCLUDED.name, category=EXCLUDED.category,
                price=EXCLUDED.price, badge=EXCLUDED.badge,
                description=EXCLUDED.description, image_url=EXCLUDED.image_url;
        """, (pid, data.get("name",""), data.get("category",""),
              data.get("price", 0), data.get("badge",""),
              data.get("description",""), data.get("imageUrl","")))
        conn.commit(); cur.close(); conn.close()
        return jsonify({"status": "ok", "id": pid}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/products/<product_id>", methods=["PUT"])
def update_product(product_id):
    if not require_admin():
        return jsonify({"error": "Accès refusé"}), 403
    data = request.get_json()
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("""
            UPDATE products SET
                name=%s, category=%s, price=%s, badge=%s,
                description=%s, image_url=%s
            WHERE id=%s;
        """, (data.get("name"), data.get("category"), data.get("price"),
              data.get("badge"), data.get("description"),
              data.get("imageUrl"), product_id))
        conn.commit(); cur.close(); conn.close()
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/products/<product_id>", methods=["DELETE"])
def delete_product(product_id):
    if not require_admin():
        return jsonify({"error": "Accès refusé"}), 403
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("DELETE FROM products WHERE id=%s;", (product_id,))
        conn.commit(); cur.close(); conn.close()
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ══════════════════════════════════════════════════════════════════════════════
# ROUTE UPLOAD IMAGE → AZURE BLOB STORAGE
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/upload", methods=["POST"])
def upload_image():
    if not require_admin():
        return jsonify({"error": "Accès refusé"}), 403

    if "file" not in request.files:
        return jsonify({"error": "Aucun fichier envoyé"}), 400

    file      = request.files["file"]
    ext       = file.filename.rsplit(".", 1)[-1].lower()
    allowed   = {"jpg", "jpeg", "png", "webp"}

    if ext not in allowed:
        return jsonify({"error": f"Format non supporté. Formats acceptés : {', '.join(allowed)}"}), 400

    blob_name    = f"products/{uuid.uuid4()}.{ext}"
    content_type = f"image/{'jpeg' if ext in ('jpg','jpeg') else ext}"

    try:
        client    = get_blob_client()
        container = client.get_container_client(BLOB_CONTAINER)
        container.upload_blob(
            name=blob_name,
            data=file.read(),
            content_settings=ContentSettings(content_type=content_type),
            overwrite=True
        )
        # URL publique de l'image
        account_name = client.account_name
        image_url = f"https://{account_name}.blob.core.windows.net/{BLOB_CONTAINER}/{blob_name}"
        return jsonify({"url": image_url, "blob": blob_name}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ══════════════════════════════════════════════════════════════════════════════
# ROUTES AUTH
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/auth/register", methods=["POST"])
def register():
    data     = request.get_json()
    name     = (data.get("name") or "").strip()
    email    = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not name or not email or not password:
        return jsonify({"error": "Tous les champs sont requis"}), 400
    if len(password) < 6:
        return jsonify({"error": "Mot de passe trop court (6 caractères min.)"}), 400

    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("SELECT id FROM users WHERE email=%s;", (email,))
        if cur.fetchone():
            return jsonify({"error": "Cet email est déjà utilisé"}), 409

        cur.execute("""
            INSERT INTO users (name, email, password)
            VALUES (%s, %s, %s) RETURNING id;
        """, (name, email, hash_password(password)))
        user_id = cur.fetchone()["id"]
        conn.commit(); cur.close(); conn.close()

        user_data = {"id": str(user_id), "name": name, "email": email}
        return jsonify({"token": make_token(user_id), "user": user_data}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/auth/login", methods=["POST"])
def login():
    data     = request.get_json()
    email    = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "Email et mot de passe requis"}), 400

    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email=%s;", (email,))
        user = cur.fetchone()
        if not user or user["password"] != hash_password(password):
            return jsonify({"error": "Email ou mot de passe incorrect"}), 401

        cur.execute("UPDATE users SET status='active' WHERE id=%s;", (user["id"],))
        conn.commit(); cur.close(); conn.close()

        user_data = {"id": str(user["id"]), "name": user["name"], "email": user["email"]}
        return jsonify({"token": make_token(user["id"]), "user": user_data})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/auth/admin", methods=["POST"])
def admin_login():
    data = request.get_json()
    if data.get("email") == ADMIN_EMAIL and data.get("password") == ADMIN_PASSWORD:
        return jsonify({"token": make_token("admin", role="admin")})
    return jsonify({"error": "Identifiants administrateur incorrects"}), 401

# ══════════════════════════════════════════════════════════════════════════════
# ROUTES COMMANDES
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/orders", methods=["POST"])
def create_order():
    payload = get_token_payload()
    if not payload:
        return jsonify({"error": "Non authentifié"}), 401

    data = request.get_json()
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("""
            INSERT INTO orders (user_id, items, total)
            VALUES (%s, %s, %s) RETURNING id;
        """, (payload["id"], json.dumps(data.get("items", [])), data.get("total", 0)))
        order_id = cur.fetchone()["id"]
        cur.execute("UPDATE users SET orders = orders + 1 WHERE id=%s;", (payload["id"],))
        conn.commit(); cur.close(); conn.close()
        return jsonify({"orderId": str(order_id), "status": "pending"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ══════════════════════════════════════════════════════════════════════════════
# ROUTES ADMIN
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/admin/stats", methods=["GET"])
def admin_stats():
    if not require_admin():
        return jsonify({"error": "Accès refusé"}), 403
    try:
        conn  = get_db()
        cur   = conn.cursor()
        today = datetime.now(timezone.utc).date()

        cur.execute("SELECT COUNT(*) as cnt FROM users;")
        total_users = cur.fetchone()["cnt"]

        cur.execute("SELECT COUNT(*) as cnt FROM users WHERE created_at::date = %s;", (today,))
        new_today = cur.fetchone()["cnt"]

        cur.execute("SELECT COUNT(*) as cnt FROM orders;")
        total_orders = cur.fetchone()["cnt"]

        cur.execute("SELECT COUNT(*) as cnt FROM products;")
        total_products = cur.fetchone()["cnt"]

        cur.close(); conn.close()
        return jsonify({
            "totalUsers":    total_users,
            "newToday":      new_today,
            "totalOrders":   total_orders,
            "totalProducts": total_products,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/users", methods=["GET"])
def admin_users():
    if not require_admin():
        return jsonify({"error": "Accès refusé"}), 403
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("SELECT id, name, email, status, orders, created_at FROM users ORDER BY created_at DESC;")
        users = [{
            "id":        str(u["id"]),
            "name":      u["name"],
            "email":     u["email"],
            "status":    u["status"],
            "orders":    u["orders"],
            "createdAt": u["created_at"].isoformat() if u["created_at"] else "",
        } for u in cur.fetchall()]
        cur.close(); conn.close()
        return jsonify({"users": users, "total": len(users)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ══════════════════════════════════════════════════════════════════════════════
# HEALTHCHECK
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/health", methods=["GET"])
def health():
    try:
        conn = get_db()
        conn.close()
        db_status = "ok"
    except Exception as e:
        db_status = str(e)
    return jsonify({
        "status":   "ok",
        "service":  "maison-luxe-flask-v2",
        "database": f"PostgreSQL — {db_status}",
        "storage":  "Azure Blob Storage",
        "vm":       "10.1.1.4"
    })

# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("[init] Initialisation PostgreSQL...")
    init_db()
    print("[init] Initialisation Azure Blob Storage...")
    init_blob_container()
    app.run(host="0.0.0.0", port=5000, debug=False)
