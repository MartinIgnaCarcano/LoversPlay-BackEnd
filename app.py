from flask import Flask, jsonify
from database import db
import models
from routes.categorias import categorias_bp
from routes.productos import productos_bp
from routes.pedidos import pedidos_bp
from routes.auth import auth_bp
from routes.pagos import pagos_bp
from routes.envios import envios_bp
from routes.contacto import contact_bp
from datetime import timedelta
from flask_jwt_extended import JWTManager
from flask_cors import CORS
import os
from flask import request
from services.email_service import send_email
from extension import mail  
from flask_migrate import Migrate


def build_db_uri():
    db_type = os.getenv("DB_TYPE", "mysql")  # mysql o sqlite (si querés fallback)
    if db_type == "sqlite":
        return "sqlite:///ecommerce.db"

    user = os.getenv("DB_USER", "root")
    password = os.getenv("DB_PASSWORD", "")  # en XAMPP root suele estar vacío
    host = os.getenv("DB_HOST", "127.0.0.1")
    port = os.getenv("DB_PORT", "3306")
    name = os.getenv("DB_NAME", "ecommerce")

    # PyMySQL driver
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{name}?charset=utf8mb4"

app = Flask(__name__)
app.config["JWT_SECRET_KEY"] = "cambia-esto-por-un-secreto-seguro"  # usa variable de entorno en prod

CORS(
  app,
  supports_credentials=True,
  resources={r"/api/*": {"origins": ["http://localhost:8000", "http://localhost:3000"]}},
  allow_headers=["Content-Type", "Authorization"],
  methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
)


# Configuración de MySQL
app.config["SQLALCHEMY_DATABASE_URI"] = build_db_uri()
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
    "pool_recycle": 280,
}

app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(seconds=3600)  # expira en 1 hora

# ====== MAIL CONFIG (BREVO) ======
app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER", "smtp-relay.brevo.com")
app.config["MAIL_PORT"] = int(os.getenv("MAIL_PORT", "587"))
app.config["MAIL_USE_TLS"] = os.getenv("MAIL_USE_TLS", "true").lower() == "true"
app.config["MAIL_USE_SSL"] = os.getenv("MAIL_USE_SSL", "false").lower() == "true"

app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")  # login SMTP Brevo
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")  # clave SMTP Brevo

# Ej: "Lovers Play <no-reply@tudominio.com>" o "Lovers Play <tu@correo.com>"
app.config["MAIL_DEFAULT_SENDER"] = os.getenv("MAIL_DEFAULT_SENDER", app.config["MAIL_USERNAME"])

# admin opcional
app.config["ADMIN_EMAIL"] = os.getenv("ADMIN_EMAIL")



db.init_app(app)
jwt = JWTManager(app)
mail.init_app(app)
migrate = Migrate(app, db)

@jwt.expired_token_loader
def expired_token_callback(jwt_header=None, jwt_payload=None):
    return jsonify({
        "error": "token_expirado",
        "mensaje": "Tu sesión expiró. Iniciá sesión nuevamente."
    }), 401

@jwt.invalid_token_loader
def invalid_token_callback(error):
    return jsonify({
        "error": "token_invalido",
        "motivo": error,
        "mensaje": "El token enviado es inválido."
    }), 422

@jwt.unauthorized_loader
def unauthorized_callback(error):
    return jsonify({
        "error": "token_faltante",
        "mensaje": "No se envió un token."
    }), 401

@jwt.token_in_blocklist_loader
def revoked_token_callback(jwt_header=None, jwt_payload=None):
    return False

@app.route("/api/test-mail", methods=["POST"])
def test_mail():
    data = request.get_json() or {}
    to = data.get("to") or os.getenv("ADMIN_EMAIL")
    if not to:
        return jsonify({"error": "Falta 'to' y no hay ADMIN_EMAIL"}), 400

    send_email(
        to=to,
        subject="Test Brevo ✅",
        html="<h2>Brevo funcionando 🎉</h2><p>Este email salió desde tu Flask.</p>",
    )
    return jsonify({"status": "ok", "sent_to": to}), 200


# Registrar rutas
app.register_blueprint(auth_bp)
app.register_blueprint(categorias_bp)
app.register_blueprint(productos_bp)
app.register_blueprint(pedidos_bp)
app.register_blueprint(pagos_bp)
app.register_blueprint(envios_bp)
app.register_blueprint(contact_bp)


if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)




#activar venv
#venv\Scripts\activate

