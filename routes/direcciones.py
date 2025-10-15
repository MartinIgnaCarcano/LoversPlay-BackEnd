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
        departamento=data.get("departamento"),
        pais=data.get("pais"),
        extra=data.get("extra")
    )

    db.session.add(nueva_direccion)
    db.session.commit()

    return jsonify({"message": "Dirección creada con éxito", "id": nueva_direccion.id}), 201

@direcciones_bp.route("/<int:direccion_id>", methods=["GET"])
def obtener_direccion(direccion_id):
    direccion = Direccion.query.get(direccion_id)
    if not direccion:
        return jsonify({"error": "Dirección no encontrada"}), 404

    return jsonify({
        "id": direccion.id,
        "usuario_id": direccion.usuario_id,
        "calle": direccion.calle,
        "provincia": direccion.provincia,
        "departamento": direccion.departamento,
        "codigo_postal": direccion.codigo_postal,
        "pais": direccion.pais,
        "extra": direccion.extra
    }), 200

@direcciones_bp.route("/", methods=["GET"])
def obtener_direcciones():
    direcciones = Direccion.query.all()
    return jsonify([{
        "id": d.id,
        "usuario_id": d.usuario_id,
        "calle": d.calle,
        "provincia": d.provincia,
        "departamento": d.departamento,
        "codigo_postal": d.codigo_postal,
        "pais": d.pais,
        "extra": d.extra
    } for d in direcciones]), 200