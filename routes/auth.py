from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token, create_refresh_token,
    jwt_required, get_jwt_identity
)
from models import Usuario, Direccion, Favorito
from database import db
from services.notifications import send_user_welcome

auth_bp = Blueprint("auth", __name__,url_prefix="/api/auth")

# -----------------------------------
# REGISTER
# -----------------------------------
@auth_bp.route("/register", methods=["POST"])
def crear_usuario():
    data = request.json or {}

    if not data.get("email") or not data.get("password"):
        return jsonify({"error": "Email y password son requeridos"}), 400

    # Verificar que no exista
    if Usuario.query.filter_by(email=data["email"]).first():
        return jsonify({"error": "El email ya está registrado"}), 400

    usuario = Usuario(
        nombre=data.get("nombre"),
        email=data["email"],
        telefono=data.get("telefono")
    )

    usuario.set_password(data["password"])

    db.session.add(usuario)
    db.session.commit()

    send_user_welcome(usuario)
    
    return jsonify({"message": "Usuario creado con éxito"}), 201


# -----------------------------------
# LOGIN
# -----------------------------------
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
    
    if isinstance(access_token, bytes):
        access_token = access_token.decode("utf-8")

    return jsonify({
        "access_token": access_token,
        "id": user.id,
        "nombre": user.nombre
    }), 200

#Me
@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def obtener_usuario():
    user = Usuario.query.get(get_jwt_identity())

    if not user:
        return jsonify({"error": "Usuario no encontrado"}), 404

    direccion = user.direccion  # SE CAMBIA A UNO A UNO

    return jsonify({
        "id": user.id,
        "nombre": user.nombre,
        "email": user.email,
        "telefono": user.telefono,
        "rol": user.rol,
        "fecha_registro": user.fecha_registro.isoformat(),
        "direccion": {
            "id": direccion.id,
            "calle": direccion.calle,
            "provincia": direccion.provincia,
            "departamento": direccion.departamento,
            "codigo_postal": direccion.codigo_postal,
            "pais": direccion.pais,
            "extra": direccion.extra
        } if direccion else None,
        "favoritos": [f.producto_id for f in user.favoritos]
        
    }), 200
    
# UPDATE USER + ADDRESS
@auth_bp.route("/me", methods=["PATCH"])
@jwt_required()
def actualizar_usuario():
    user = Usuario.query.get(get_jwt_identity())

    if not user:
        return jsonify({"error": "Usuario no encontrado"}), 404

    data = request.get_json() or {}

    # ----------- UPDATE USER -----------
    if "nombre" in data:
        user.nombre = data["nombre"]

    if "telefono" in data:
        user.telefono = data["telefono"]

    if "email" in data:
        if Usuario.query.filter(Usuario.email == data["email"], Usuario.id != user.id).first():
            return jsonify({"error": "Ese email ya está en uso por otro usuario"}), 400
        user.email = data["email"]

    if "password" in data:
        user.set_password(data["password"])

    # ----------- UPDATE OR CREATE ADDRESS -----------
    if "direccion" in data:
        d = data["direccion"]

        # Ver si ya tiene 1 dirección
        if user.direccion:
            user.direccion.calle = d.get("calle", user.direccion.calle)
            user.direccion.provincia = d.get("provincia", user.direccion.provincia)
            user.direccion.codigo_postal = d.get("codigo_postal", user.direccion.codigo_postal)
            user.direccion.pais = d.get("pais", user.direccion.pais)
            user.direccion.extra = d.get("extra", user.direccion.extra)
            user.direccion.departamento = d.get("departamento", user.direccion.departamento)
        else:
            nueva = Direccion(
                usuario_id=user.id,
                calle=d.get("calle"),
                provincia=d.get("provincia"),
                codigo_postal=d.get("codigo_postal"),
                pais=d.get("pais"),
                extra=d.get("extra"),
                departamento=d.get("departamento")
            )
            db.session.add(nueva)

    db.session.commit()

    return jsonify({"message": "Usuario actualizado con éxito"}), 200
    
@auth_bp.route('/islogged', methods=['GET'])
@jwt_required()
def protegido():
    usuario_id = get_jwt_identity()
    return jsonify({"mensaje": f"Acceso concedido al usuario {usuario_id}"})

@auth_bp.route("/fav/<int:id>", methods=["POST"])
@jwt_required()
def agregarFavorito(id):
    current = get_jwt_identity()  
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

@auth_bp.route("/mis-productos", methods=["GET"])
@jwt_required()
def obtener_favoritos_completos():
    user_id = get_jwt_identity()

    favoritos = Favorito.query.filter_by(usuario_id=user_id).all()

    productos = []
    for f in favoritos:
        p = f.producto  # ahora sí existe

        productos.append({
            "id": p.id,
            "nombre": p.nombre,
            "precio": p.precio,
            "url_imagen_principal": p.url_imagen_principal,
            "url_imagen_secundaria": p.imagenes[0].url_imagen if p.imagenes else None,
            "stock": p.stock,
            "vistas": p.vistas,
            "valoracion_promedio": p.valoracion_promedio,
        })

    return jsonify(productos), 200

@auth_bp.route("/deletefav/<int:id>", methods=["DELETE"])
@jwt_required()
def eliminar_favorito(id):
    try:
        current = get_jwt_identity()
        print("Fav eliminar ", id)
        
        favorito = Favorito.query.filter_by(usuario_id=current,producto_id=id).first()

        db.session.delete(favorito)
        db.session.commit()
    
        return jsonify({
            "message": "Favorito eliminado correctamente"
        })
    except:
        return jsonify({
            "message": "Error al eliminar favorito"
        }), 500

# -----------------------------------
# CRUD
# -----------------------------------

#Listar usuarios
@auth_bp.route("/listar", methods=["GET"])
@jwt_required()
def listar_usuarios():
    try:
        # Paginación
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 10))
        offset_value = (page - 1) * per_page

        # Filtro activo (opcional)
        activo_param = request.args.get("activo")  # "true" | "false" | None

        query = Usuario.query

        if activo_param is not None:
            activo_bool = activo_param.lower() == "true"
            query = query.filter(Usuario.activo == activo_bool)

        # Total con filtros aplicados
        total = query.count()

        usuarios = (
            query
            .order_by(Usuario.id.asc())
            .limit(per_page)
            .offset(offset_value)
            .all()
        )

        data = []
        for user in usuarios:
            direccion = user.direccion
            data.append({
                "id": user.id,
                "nombre": user.nombre,
                "email": user.email,
                "telefono": user.telefono,
                "rol": user.rol,
                "fecha_registro": user.fecha_registro.isoformat() if user.fecha_registro else None,
                "activo": user.activo,
                "direccion": {
                    "id": direccion.id,
                    "calle": direccion.calle,
                    "provincia": direccion.provincia,
                    "departamento": direccion.departamento,
                    "codigo_postal": direccion.codigo_postal,
                    "pais": direccion.pais,
                    "extra": direccion.extra
                } if direccion else None
            })

        return jsonify({
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": (total + per_page - 1) // per_page,
            "usuarios": data
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@auth_bp.route("/<int:id>", methods=["GET"])
@jwt_required()
def obtener_usuario_admin(id):
    user = Usuario.query.get(id)

    if not user:
        return jsonify({"error": "Usuario no encontrado"}), 404

    direccion = user.direccion  # SE CAMBIA A UNO A UNO

    return jsonify({
        "id": user.id,
        "nombre": user.nombre,
        "email": user.email,
        "telefono": user.telefono,
        "rol": user.rol,
        "activo": user.activo,
        "fecha_registro": user.fecha_registro.isoformat(),
        "direccion": {
            "id": direccion.id,
            "calle": direccion.calle,
            "provincia": direccion.provincia,
            "departamento": direccion.departamento,
            "codigo_postal": direccion.codigo_postal,
            "pais": direccion.pais,
            "extra": direccion.extra
        } if direccion else None,
        "favoritos": [f.producto_id for f in user.favoritos]
        
    }), 200

@auth_bp.route("/<int:id>", methods=["PATCH"])
@jwt_required()
def actualizar_usuario_admin(id):
    user = Usuario.query.get(id)

    if not user:
        return jsonify({"error": "Usuario no encontrado"}), 404

    data = request.get_json() or {}

    # ----------- UPDATE USER -----------
    if "nombre" in data:
        user.nombre = data["nombre"]

    if "telefono" in data:
        user.telefono = data["telefono"]

    if "email" in data:
        if Usuario.query.filter(Usuario.email == data["email"], Usuario.id != user.id).first():
            return jsonify({"error": "Ese email ya está en uso por otro usuario"}), 400
        user.email = data["email"]

    if "password" in data:
        user.set_password(data["password"])

    # ----------- UPDATE OR CREATE ADDRESS -----------
    if "direccion" in data:
        d = data["direccion"]

        # Ver si ya tiene 1 dirección
        if user.direccion:
            user.direccion.calle = d.get("calle", user.direccion.calle)
            user.direccion.provincia = d.get("provincia", user.direccion.provincia)
            user.direccion.codigo_postal = d.get("codigo_postal", user.direccion.codigo_postal)
            user.direccion.pais = d.get("pais", user.direccion.pais)
            user.direccion.extra = d.get("extra", user.direccion.extra)
            user.direccion.departamento = d.get("departamento", user.direccion.departamento)
        else:
            nueva = Direccion(
                usuario_id=user.id,
                calle=d.get("calle"),
                provincia=d.get("provincia"),
                codigo_postal=d.get("codigo_postal"),
                pais=d.get("pais"),
                extra=d.get("extra"),
                departamento=d.get("departamento")
            )
            db.session.add(nueva)

    if "activo" in data:
        a = data["activo"]
        if a==True:
            user.activo = True
        else:
            user.activo = False
    
    db.session.commit()

    return jsonify({"message": "Usuario actualizado con éxito"}), 200

@auth_bp.route("/<int:id>", methods=["DELETE"])
@jwt_required()
def eliminar_usuario(id):
    user = Usuario.query.get(id)
    if not user:
        return jsonify({"error": "Usuario no encontrado"}),404
    user.activo = False
    db.session.add(user)
    db.session.commit()
    return jsonify({
        "msg":"Usuario eliminado correctamente"
    })    