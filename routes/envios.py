from flask import Blueprint, request, jsonify
from models import ZonaEnvio
from database import db

envios_bp = Blueprint("zona_envios", __name__, url_prefix="/api/envios")

@envios_bp.route("/", methods=["GET"])
def listar_zonas():
    zonas = ZonaEnvio.query.all()
    return jsonify([z.to_dict() for z in zonas])

@envios_bp.route("/<int:zona_id>", methods=["GET"])
def obtener_zona(zona_id):
    zona = ZonaEnvio.query.get(zona_id)
    if not zona:
        return jsonify({"error": "Zona no encontrada"}), 404
    return jsonify(zona.to_dict())

@envios_bp.route("/", methods=["POST"])
def crear_zona():
    data = request.get_json()

    zona = ZonaEnvio(
        nombre=data["nombre"],
        cp_inicio=data["cp_inicio"],
        cp_fin=data["cp_fin"],
        tipo_envio=data["tipo_envio"],
        precio=data["precio"],
        activa = True
    )

    db.session.add(zona)
    db.session.commit()

    return jsonify({"message": "Zona creada", "zona": zona.to_dict()}), 201

@envios_bp.route("/<int:zona_id>", methods=["PUT", "PATCH"])
def actualizar_zona(zona_id):
    zona = ZonaEnvio.query.get(zona_id)
    if not zona:
        return jsonify({"error": "Zona no encontrada"}), 404

    data = request.get_json()
    if "nombre" in data:
        zona.nombre = data.get("nombre")
    
    if "cp_inicio" in data:
        zona.cp_inicio = data.get("cp_inicio")
    
    if "cp_fin" in data:
        zona.cp_fin = data.get("cp_fin")
            
    if "tipo_envio" in data:
        zona.tipo_envio = data.get("tipo_envio")
        
    if "precio" in data:
        zona.precio = data.get("precio")
        
    if "activa" in data:
        zona.activa = data.get("activa")
    
    db.session.commit()

    return jsonify({"message": "Zona actualizada", "zona": zona.to_dict()})

@envios_bp.route("/<int:zona_id>", methods=["DELETE"])
def eliminar_zona(zona_id):
    zona = ZonaEnvio.query.get(zona_id)
    if not zona:
        return jsonify({"error": "Zona no encontrada"}), 404

    db.session.delete(zona)
    db.session.commit()

    return jsonify({"message": "Zona eliminada"})

@envios_bp.route("/calcular", methods=["POST"])
def calcular_envio():
    data = request.get_json()
    cp = data.get("cp")
    tipo_envio = data.get("tipo_envio")

    if not cp or not tipo_envio:
        return jsonify({"error": "codigo_postal y tipo_envio son requeridos"}), 400

    zona = ZonaEnvio.query.filter(
        ZonaEnvio.cp_inicio <= cp,
        ZonaEnvio.cp_fin >= cp,
        ZonaEnvio.tipo_envio == tipo_envio,
        ZonaEnvio.activa == True
    ).first()

    if not zona:
        return jsonify({"error": "No hay tarifas para este CP y tipo de envío"}), 404

    return jsonify({
        "zona": zona.nombre,
        "tipo_envio": tipo_envio,
        "precio": zona.precio
    }), 200
