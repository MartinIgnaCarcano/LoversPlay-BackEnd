from flask import Blueprint, request, jsonify

from models import Usuario, Direccion
from database import db

direcciones_bp = Blueprint("direcciones", __name__, url_prefix="/api/direcciones")

# Crear direccion
@direcciones_bp.route("/", methods=["POST"])
def crear_direccion():
    data = request.get_json()
    usuario_id = data.get("usuario_id")
    if not usuario_id:
        return jsonify({"error": "usuario_id es requerido"}), 400

    nueva_direccion = Direccion(
        usuario_id=usuario_id,
        calle=data.get("calle"),
        provincia=data.get("provincia"),
        codigo_postal=data.get("codigo_postal"),
        pais=data.get("pais"),
        extra=data.get("extra")
    )

    db.session.add(nueva_direccion)
    db.session.commit()

    return jsonify({"message": "Dirección creada con éxito", "id": nueva_direccion.id}), 201