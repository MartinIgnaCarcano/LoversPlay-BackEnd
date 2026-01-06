from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import Pedido, PedidoDetalle, Producto, Usuario, Pago
from database import db
from sqlalchemy import desc

pedidos_bp = Blueprint("pedidos", __name__,url_prefix="/api/pedidos")

# Listar pedidos del usuario logueado
@pedidos_bp.route("/", methods=["GET"], strict_slashes=False)
@jwt_required()
def listar_pedidos():
    try:
        usuario_id = get_jwt_identity()
        
        if usuario_id is None:
            return jsonify({"error": "Usuario no autenticado"}), 401
        
        pedidos = Pedido.query.filter_by(usuario_id=usuario_id).all()
        return jsonify([
            {
                "id": p.id,
                "estado": p.estado,
                "total": p.total,
                "costo_envio": p.costo_envio,
                "fecha": p.fecha.isoformat(),
                "estado_pago":(Pago.query
                                .filter_by(pedido_id=p.id)
                                .order_by(Pago.fecha_creacion.desc())
                                .first()).estado,
                "detalles": [
                    {
                        "producto": i.producto.nombre,
                        "cantidad": i.cantidad,
                        "subtotal": i.subtotal
                    } for i in p.detalles
                ]
            } for p in pedidos
        ])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Listar pedidos del usuario logueado
@pedidos_bp.route("/listar", methods=["GET"])
@jwt_required()
def listar_todos_pedidos():
    try:
        page = int(request.args.get("page", 1))       # Página actual (default 1)
        per_page = int(request.args.get("per_page", 10))  # Productos por página (default 10)
        
        offset_value = (page - 1) * per_page

        pedidos = (
            Pedido.query
            .order_by(desc(Pedido.fecha))
            .limit(per_page)
            .offset(offset_value)
            .all()
        )
        total = Pedido.query.count()
        
        return jsonify(
            {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pedidos": [
                    {
                        "id": p.id,
                        "estado": p.estado,
                        "total": p.total,
                        "costo_envio": p.costo_envio,
                        "fecha": p.fecha.isoformat(),
                        "detalles": [
                            {
                                "producto": i.producto.nombre,
                                "cantidad": i.cantidad,
                                "subtotal": i.subtotal
                            } for i in p.detalles
                            ]
                    }for p in pedidos
                ]
            } 
                
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Ver detalle de un pedido
@pedidos_bp.route("/unico/<int:id>", methods=["GET"])
def detalle_pedido(id):
    pedido = Pedido.query.get(id)
    if not pedido:
        return jsonify({"error": "Pedido no encontrado"}), 404
    pago = (Pago.query
        .filter_by(pedido_id=pedido.id)
        .order_by(Pago.fecha_creacion.desc())
        .first())
    
    return jsonify({
        "id": pedido.id,
        "estado": pedido.estado,
        "total": pedido.total,
        "costo_envio": pedido.costo_envio,
        "fecha": pedido.fecha.isoformat(),
        "estado_pago":pago.estado,
        "detalles": [
            {
                "producto": i.producto.nombre,
                "cantidad": i.cantidad,
                "subtotal": i.subtotal
            } for i in pedido.detalles
        ]
    })

# Actualizar estado del pedido (solo admin para cambiar a ENVIADO o ENTREGADO)
@pedidos_bp.route("/<int:id>", methods=["PATCH"])
@jwt_required()
def actualizar_pedido(id):
    user_id = get_jwt_identity()
    user = Usuario.query.get(user_id)
    
    if not user or user.rol != "ADMIN":
        return jsonify({"error": "acceso denegado"}), 404
    
    data = request.get_json() or {}
    pedido = Pedido.query.get_or_404(id)

    # Solo admin puede cambiar estado
    if "estado" in data:
        pedido.estado = data["estado"]

    db.session.commit()
    return jsonify({"message": "Pedido actualizado", "estado": pedido.estado})

@pedidos_bp.route("/<int:id>", methods=["DELETE"])
@jwt_required()
def eliminar_pedido(id):
    user_id = get_jwt_identity()
    user = Usuario.query.get(user_id)
    if not user or user.rol != "ADMIN":
        return jsonify({"error": "acceso denegado"}), 404

    pedido = Pedido.query.get(id)
    
    if not pedido:
        return jsonify({"error": "Pedido no encontrado"}), 404
    db.session.delete(pedido)
    db.session.commit()
    return jsonify({"message": "Pedido eliminado"}), 204

# Crear un pedido manual (sin mp por el momento)
@pedidos_bp.route("/", methods=["POST"])
def crear_pedido():
    try:
        data = request.get_json()
        detalles = data.get("detalles", [])

        if not detalles:
            return jsonify({"error": "Faltan detalles del pedido"}), 400

        # ================================================================
        # 1) Intentar obtener usuario LOGEADO
        # ================================================================
        usuario_id = None
        try:
            usuario_id = get_jwt_identity()
        except:
            pass  # si no hay token, get_jwt_identity() levanta error silencioso

        # ================================================================
        # 2) Si NO está logeado → buscar o crear usuario invitado
        # ================================================================
        if not usuario_id:
            email = data.get("email")
            nombre = data.get("nombre", "Invitado")
            telefono = data.get("telefono")

            if not email:
                return jsonify({"error": "Para pedidos sin registrarse, se requiere email"}), 400

            # Buscar si ya existe ese email
            usuario = Usuario.query.filter_by(email=email).first()

            # Crear invitado si no existe
            if not usuario:
                usuario = Usuario(
                    nombre=nombre,
                    email=email,
                    telefono=telefono,
                    rol="guest",
                    password_hash=""   # sin contraseña
                )
                db.session.add(usuario)
                db.session.commit()

            usuario_id = usuario.id
        
        # ================================================================
        # 3) Crear pedido normal
        # ================================================================
        total = 0
        detalles_pedido = []

        for item in detalles:
            producto = Producto.query.get(item["producto_id"])
            if not producto:
                return jsonify({"error": f"Producto {item['producto_id']} no encontrado"}), 404

            cantidad = item.get("cantidad", 1)

            if cantidad > producto.stock:
                return jsonify({"error": f"Stock insuficiente para {producto.nombre}"}), 400
            
            producto.stock -= cantidad
            subtotal = producto.precio * cantidad
            total += subtotal

            detalles_pedido.append(
                PedidoDetalle(
                    producto_id=producto.id,
                    cantidad=cantidad,
                    subtotal=subtotal
                )
            )
            
        #Sumamos el envio al costo total del pedido
        costo_envio = data.get("costo_envio", 0)
        total_final = total + costo_envio
        
        pedido = Pedido(
            usuario_id=usuario_id,
            total=total_final,
            costo_envio=costo_envio,
            estado="PENDIENTE",
            detalles=detalles_pedido
        )

        db.session.add(pedido)
        db.session.commit()

        return jsonify({
            "pedido_id": pedido.id,
            "total": total_final,
            "estado": pedido.estado,
            "usuario_id": usuario_id
        }), 201

    except Exception as e:
        print("ERROR:", e)
        return jsonify({"error": str(e)}), 500


