from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import Pedido, PedidoDetalle, Producto, Usuario, Pago
from database import db
from sqlalchemy import desc
from services.notifications import send_admin_new_order, send_user_order_created
from datetime import datetime, timedelta
from sqlalchemy import update
from decimal import Decimal
from sqlalchemy import update

pedidos_bp = Blueprint("pedidos", __name__,url_prefix="/api/pedidos")

def require_admin():
    user_id = get_jwt_identity()
    user = Usuario.query.get(int(user_id))
    if not user or user.rol != "admin":
        return None
    return user

#1440 minutos = 24hs
RESERVA_MINUTOS = 1440

#-----------------
#-----USER--------
#-----------------
@pedidos_bp.route("/", methods=["GET"], strict_slashes=False) # Listar pedidos del usuario logueado
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
                "estado_pago": (
                    (Pago.query
                        .filter_by(pedido_id=p.id)
                        .order_by(Pago.fecha_creacion.desc())
                        .first()
                    ).estado
                    if (Pago.query
                        .filter_by(pedido_id=p.id)
                        .order_by(Pago.fecha_creacion.desc())
                        .first()
                    ) else None
                ),
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

# Ver detalle de un pedido
@pedidos_bp.route("/unico/<int:id>", methods=["GET"])
@jwt_required()
def detalle_pedido(id):
    try:
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
            "estado_pago": pago.estado if pago else None,
            "detalles": [
                {
                    "producto": i.producto.nombre,
                    "cantidad": i.cantidad,
                    "subtotal": i.subtotal
                } for i in pedido.detalles
            ]
        })
    except Exception as e:
        db.session.rollback()
        print("ERROR:", repr(e))
        return jsonify({"error": "Error interno"}), 500    

@pedidos_bp.route("/", methods=["POST"])
@jwt_required(optional=True)
def crear_pedido():
    try:
        data = request.get_json() or {}
        detalles = data.get("detalles", [])
        if not detalles:
            return jsonify({"error": "Faltan detalles del pedido"}), 400

        # 1) usuario logueado o invitado
        usuario_id = get_jwt_identity()
        usuario = None

        if not usuario_id:
            email = data.get("email")
            nombre = data.get("nombre", "Invitado")
            telefono = data.get("telefono")

            if not email:
                return jsonify({"error": "Para pedidos sin registrarse, se requiere email"}), 400

            usuario = Usuario.query.filter_by(email=email).first()
            if not usuario:
                usuario = Usuario(
                    nombre=nombre,
                    email=email,
                    telefono=telefono,
                    rol="guest",
                    password_hash=f"guest.{telefono or ''}"
                )
                db.session.add(usuario)
                db.session.flush()  # <-- NO commit todavía

            usuario_id = usuario.id
        else:
            usuario_id = int(usuario_id)
            usuario = Usuario.query.get(usuario_id)

        # 2) reservar stock y armar detalles (todo en la misma transacción)
        total = Decimal("0.00")
        detalles_pedido = []

        for item in detalles:
            producto_id = item.get("producto_id")
            cantidad = int(item.get("cantidad", 1))

            if not producto_id or cantidad <= 0:
                db.session.rollback()
                return jsonify({"error": "Detalle inválido"}), 400

            # Traer producto (precio/nombre) - lectura
            producto = Producto.query.get(producto_id)
            if not producto or not producto.activo:
                db.session.rollback()
                return jsonify({"error": f"Producto {producto_id} no encontrado"}), 404

            # ✅ UPDATE ATÓMICO: descuenta solo si hay stock suficiente
            stmt = (
                update(Producto)
                .where(Producto.id == producto_id, Producto.stock >= cantidad)
                .values(stock=Producto.stock - cantidad)
            )
            res = db.session.execute(stmt)

            if res.rowcount == 0:
                db.session.rollback()
                return jsonify({"error": f"Stock insuficiente para {producto.nombre}"}), 400

            # subtotal usando Decimal (evita errores float)
            unit_price = Decimal(str(producto.precio))
            subtotal = (unit_price * Decimal(cantidad)).quantize(Decimal("0.01"))
            total += subtotal

            detalles_pedido.append(
                PedidoDetalle(
                    producto_id=producto_id,
                    cantidad=cantidad,
                    subtotal=float(subtotal)  # si tu columna es Numeric podés guardar Decimal directo
                )
            )

        costo_envio = Decimal(str(data.get("costo_envio", 0) or 0)).quantize(Decimal("0.01"))
        total_final = (total + costo_envio).quantize(Decimal("0.01"))

        pedido = Pedido(
            usuario_id=usuario_id,
            total=float(total_final),       # si Numeric: total=total_final
            costo_envio=float(costo_envio), # si Numeric: costo_envio=costo_envio
            estado="PENDIENTE_PAGO",
            detalles=detalles_pedido,
            expires_at=datetime.utcnow() + timedelta(minutes=RESERVA_MINUTOS),
            stock_state="reserved"
        )

        db.session.add(pedido)

        # ✅ un solo commit al final: usuario guest + stock + pedido + detalles
        db.session.commit()

        # mails
        if usuario and usuario.email:
            send_user_order_created(usuario, pedido)
        send_admin_new_order(pedido, usuario)

        return jsonify({
            "pedido_id": pedido.id,
            "total": float(total_final),
            "estado": pedido.estado,
            "usuario_id": usuario_id
        }), 201

    except Exception as e:
        db.session.rollback()
        print("ERROR:", repr(e))
        return jsonify({"error": "Error interno"}), 500


#-----------------
#----ADMIN--------
#-----------------
@pedidos_bp.route("/listar", methods=["GET"])
@jwt_required()
def listar_todos_pedidos():
    admin = require_admin()
    if not admin:
        return jsonify({"error": "Acceso denegado"}), 403
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

@pedidos_bp.route("/<int:id>", methods=["PATCH"]) # Actualizar estado del pedido
@jwt_required()
def actualizar_pedido(id):
    admin = require_admin()
    if not admin:
        return jsonify({"error": "Acceso denegado"}), 403
    
    try:
        data = request.get_json() or {}
        pedido = Pedido.query.get_or_404(id)

        # Solo admin puede cambiar estado
        if "estado" in data:
            pedido.estado = data["estado"]

        db.session.commit()
        return jsonify({"message": "Pedido actualizado", "estado": pedido.estado})
    except Exception as e:
        db.session.rollback()
        print("ERROR:", repr(e))
        return jsonify({"error": "Error interno"}), 500

@pedidos_bp.route("/<int:id>", methods=["DELETE"])
@jwt_required()
def eliminar_pedido(id):
    admin = require_admin()
    if not admin:
        return jsonify({"error": "Acceso denegado"}), 403
    
    try:
        pedido = Pedido.query.get(id)
        
        if not pedido:
            return jsonify({"error": "Pedido no encontrado"}), 404
        db.session.delete(pedido)
        db.session.commit()
        return jsonify({"message": "Pedido eliminado"}), 204
    except Exception as e:
        db.session.rollback()
        print("ERROR:", repr(e))
        return jsonify({"error": "Error interno"}), 500
    
@pedidos_bp.route("/expirar", methods=["POST"])
@jwt_required()
def expirar_pedidos():
    
    try:
        now = datetime.utcnow()

        expirables = (
            Pedido.query
            .filter(Pedido.estado == "PENDIENTE_PAGO")
            .filter(Pedido.expires_at.isnot(None))
            .filter(Pedido.expires_at < now)
            .all()
        )

        expired_ids = []
        released_stock_for = []

        for pedido in expirables:
            # idempotencia: si ya liberaste stock, no repetir
            if pedido.stock_state != "reserved":
                pedido.estado = "EXPIRADO"
                expired_ids.append(pedido.id)
                continue

            # devolver stock según detalles
            for d in pedido.detalles:
                prod = Producto.query.get(d.producto_id)
                if prod:
                    prod.stock += int(d.cantidad)

            pedido.stock_state = "released"
            pedido.estado = "EXPIRADO"

            expired_ids.append(pedido.id)
            released_stock_for.append(pedido.id)

        db.session.commit()

        return jsonify({
            "now_utc": now.isoformat(),
            "found": len(expirables),
            "expired": len(expired_ids),
            "released_stock_for": released_stock_for,
            "expired_ids": expired_ids
        }), 200
    except Exception as e:
        db.session.rollback()
        print("ERROR:", repr(e))
        return jsonify({"error": "Error interno"}), 500
    
    