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
import flask_jwt_extended
print("VERSIÓN JWT:", flask_jwt_extended.__version__)

app = Flask(__name__)
app.config["JWT_SECRET_KEY"] = "cambia-esto-por-un-secreto-seguro"  # usa variable de entorno en prod
print("SECRET:", app.config['JWT_SECRET_KEY'])

CORS(app, supports_credentials=True, origins=["http://192.168.100.219:3000", "*"])


# Configuración de SQLite
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///ecommerce.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(seconds=3600)  # expira en 1 hora

db.init_app(app)
jwt = JWTManager(app)

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