from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required
from models import Usuario
from database import db

usuarios_bp = Blueprint("usuarios", __name__,url_prefix="/api/usuarios")

# @usuarios_bp.route("/", methods=["GET"])
# def listar_usuarios():
    usuarios = Usuario.query.all()
    return jsonify([
        {
            "id": u.id,
            "nombre": u.nombre,
            "email": u.email,
            "rol": u.rol,
            "creado_en": u.creado_en.isoformat()
        }
        for u in usuarios
    ])

@usuarios_bp.route("/<int:id>", methods=["GET"])
def obtener_usuario(id):
    user = Usuario.query.get(id)
    if not user:
        return jsonify({"error": "Usuario no encontrado"}), 404

    return jsonify({
        "id": user.id,
        "nombre": user.nombre,
        "email": user.email,
        "direccion": user.direccion,
        "telefono": user.telefono,
        "rol": user.rol,
        "creado_en": user.creado_en.isoformat()
    })
    
@usuarios_bp.route("/", methods=["PATCH"])
@jwt_required()
def actualizar_usuario():
    current = get_jwt_identity()  # dict con {id, email, rol}
    user = Usuario.query.get(current)

    if not user:
        return jsonify({"error": "Usuario no encontrado"}), 404

    data = request.get_json() or {}

    # Solo actualizamos los campos permitidos si vienen en la request
    if "nombre" in data:
        user.nombre = data["nombre"]

    if "direccion" in data:
        user.direccion = data["direccion"]

    if "telefono" in data:
        user.telefono = data["telefono"]

    if "password" in data:
        user.set_password(data["password"])

    db.session.commit()

    return jsonify({
        "message": "Usuario actualizado",
        "user": {
            "id": user.id,
            "nombre": user.nombre,
            "email": user.email,
            "direccion": user.direccion,
            "telefono": user.telefono,
            "rol": user.rol
        }
    }), 200