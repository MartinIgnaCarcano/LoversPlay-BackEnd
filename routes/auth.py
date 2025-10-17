from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token, create_refresh_token,
    jwt_required, get_jwt_identity
)
from models import Usuario, Direccion, Favorito
from database import db

auth_bp = Blueprint("auth", __name__,url_prefix="/api/auth")

@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"error": "Email y password son requeridos"}), 400

    user = Usuario.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return jsonify({"error": "Credenciales inválidas"}), 401

    
    access_token = create_access_token(identity=str(user.id))

    return jsonify({
        "access_token": access_token
    }), 200

@auth_bp.route("/register", methods=["POST"])
def crear_usuario():
    data = request.json
    if not data.get("email") or not data.get("password"):
        return jsonify({"error": "Email y password son requeridos"}), 400

    if Usuario.query.filter_by(email=data["email"]).first():
        return jsonify({"error": "El email ya está registrado"}), 400

    nuevo_usuario = Usuario(
        nombre=data.get("nombre"),
        email=data["email"],
        fecha_registro=db.func.now(),
        telefono=data.get("telefono")   
    )
    nuevo_usuario.set_password(data["password"])

    db.session.add(nuevo_usuario)
    db.session.commit()

    return jsonify({"message": "Usuario creado con éxito"}), 201

@auth_bp.route("/", methods=["GET"])
def listar_usuarios():
    usuarios = Usuario.query.all()
    return jsonify([
        {
            "id": u.id,
            "nombre": u.nombre,
            "email": u.email,
            "fecha_registro": u.fecha_registro.isoformat()
        }
        for u in usuarios
    ])

@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def obtener_usuario():
    user = Usuario.query.get(get_jwt_identity())
    if not user:
        return jsonify({"error": "Usuario no encontrado"}), 404

    return jsonify({
        "id": user.id,
        "nombre": user.nombre,
        "email": user.email,
        "direcciones": [{
            "id": d.id,
            "usuario_id": d.usuario_id,
            "calle": d.calle,
            "provincia": d.provincia,
            "departamento": d.departamento,
            "codigo_postal": d.codigo_postal,
            "pais": d.pais,
            "extra": d.extra
        } for d in user.direcciones],
        "telefono": user.telefono,
        "rol": user.rol,
        "fecha_registro": user.fecha_registro.isoformat()
    }), 200

@auth_bp.route("/", methods=["PATCH"])
@jwt_required()
def actualizar_usuario():
    user = Usuario.query.get(get_jwt_identity())

    if not user:
        return jsonify({"error": "Usuario no encontrado"}), 404

    data = request.get_json() or {}

    if "nombre" in data:
        user.nombre = data["nombre"]

    if "telefono" in data:
        user.telefono = data["telefono"]

    if "password" in data:
        user.set_password(data["password"])

    if "email" in data:
        user.email = data["email"]
        
    if "direccion" in data:
        calle, codigo_postal, provincia, pais = [x.strip() for x in data["direccion"].split(",")]
        nueva_direccion = Direccion(
                calle=calle,
                codigo_postal=codigo_postal,
                provincia=provincia,
                pais=pais,
                usuario_id=user.id
            )
        
        db.session.add(nueva_direccion)
        pass
    
    db.session.commit()

    return jsonify({
        "message": "Usuario actualizado",
        "user": {
            "id": user.id,
            "nombre": user.nombre,
            "email": user.email,
            "telefono": user.telefono,
            "rol": user.rol
        }
    }), 200
    
@auth_bp.route('/islogged', methods=['GET'])
@jwt_required()
def protegido():
    usuario_id = get_jwt_identity()
    return jsonify({"mensaje": f"Acceso concedido al usuario {usuario_id}"})

@auth_bp.route("/<int:id>", methods=["POST"])
@jwt_required()
def agregarFavorito(id):
    current = get_jwt_identity()  # dict con {id, email, rol}
    user = Usuario.query.get(current)

    if not user:
        return jsonify({"error": "Usuario no encontrado"}), 404
    
    favorito = Favorito(
        usuario_id=user.id,
        producto_id=id
    )
    db.session.add(favorito)
    db.session.commit()

    return jsonify({
        "message": "Producto agregado a favoritos",
        "favorito": {
            "id": favorito.id,
            "usuario_id": favorito.usuario_id,
            "producto_id": favorito.producto_id
        }
    }), 200
