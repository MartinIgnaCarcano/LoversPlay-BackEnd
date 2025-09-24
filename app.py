from flask import Flask, jsonify
from database import db
from routes.categorias import categorias_bp
from routes.productos import productos_bp
from routes.pedidos import pedidos_bp
from routes.auth import auth_bp
from routes.pagos import pagos_bp
from routes.direcciones import direcciones_bp
from datetime import timedelta
from flask_jwt_extended import JWTManager
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "http://localhost:3000"}}, supports_credentials=True)


# Configuración de SQLite
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///ecommerce.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

app.config["JWT_SECRET_KEY"] = "cambia-esto-por-un-secreto-seguro"  # usa variable de entorno en prod
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(seconds=3600)  # expira en 1 hora

db.init_app(app)
jwt = JWTManager(app)

# Cuando el token está vencido
@jwt.expired_token_loader
def token_expirado_callback(jwt_header, jwt_payload):
    return jsonify({
        "error": "token_expirado",
        "mensaje": "Tu sesión ha caducado. Por favor, volvé a iniciar sesión."
    }), 401

# Cuando falta el token
@jwt.unauthorized_loader
def token_faltante_callback(err_str):
    return jsonify({
        "error": "token_faltante",
        "mensaje": "No se proporcionó un token de acceso."
    }), 401

# Cuando el token es inválido (malformado o corrupto)
@jwt.invalid_token_loader
def token_invalido_callback(err_str):
    return jsonify({
        "error": "token_invalido",
        "mensaje": "El token de acceso no es válido."
    }), 422

# Cuando el token es revocado (si manejás blacklist)
@jwt.revoked_token_loader
def token_revocado_callback(jwt_header, jwt_payload):
    return jsonify({
        "error": "token_revocado",
        "mensaje": "El token fue revocado."
    }), 401

# Registrar rutas
app.register_blueprint(auth_bp)
app.register_blueprint(categorias_bp)
app.register_blueprint(productos_bp)
app.register_blueprint(pedidos_bp)
app.register_blueprint(pagos_bp)
app.register_blueprint(direcciones_bp)
# Crear tablas al iniciar
with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)


#activar venv
#venv\Scripts\activate