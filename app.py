from flask import Flask, jsonify
from database import db
from routes.categorias import categorias_bp
from routes.productos import productos_bp
from routes.pedidos import pedidos_bp
from routes.auth import auth_bp
from routes.pagos import pagos_bp
from routes.envios import envios_bp
from datetime import timedelta
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from flask_mail import Mail
import flask_jwt_extended
import os
from flask import request
from services.email_service import send_email
from extension import mail  
print("VERSIÓN JWT:", flask_jwt_extended.__version__)


app = Flask(__name__)
app.config["JWT_SECRET_KEY"] = "cambia-esto-por-un-secreto-seguro"  # usa variable de entorno en prod
print("SECRET:", app.config['JWT_SECRET_KEY'])

CORS(app, supports_credentials=True, origins=["http://localhost:3000", "*"])


# Configuración de SQLite
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///ecommerce.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(seconds=86400)  # expira en 1 hora

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
# Crear tablas al iniciar
with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)


#activar venv
#venv\Scripts\activate

