from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import Pedido, PedidoDetalle, Producto, Usuario
from database import db
import mercadopago

pedidos_bp = Blueprint("pedidos", __name__,url_prefix="/api/pedidos")
# sdk = mercadopago.SDK("TEST-6608167090676875-091814-964957d986e21eee913f06709c51abeb-2611950632")

# Listar pedidos del usuario logueado
@pedidos_bp.route("/", methods=["GET"], strict_slashes=False)
@jwt_required()
def listar_pedidos():
    try:
        if usuario_id := get_jwt_identity() is None:
            return jsonify({"error": "Usuario no autenticado"}), 401
        usuario_id = get_jwt_identity()
        pedidos = Pedido.query.filter_by(usuario_id=usuario_id).all()
        return jsonify([
            {
                "id": p.id,
                "estado": p.estado,
                "total": p.total,
                "fecha": p.fecha.isoformat(),
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

# Crear un pedido manual (sin mp por el momento)
@pedidos_bp.route("/", methods=["POST"])
@jwt_required()
def crear_pedido_con_pago():
    try:
        data = request.get_json()
        usuario_id = get_jwt_identity()
        detalles = data.get("detalles", [])

        if not usuario_id or not detalles:
            return jsonify({"error": "Faltan datos (usuario_id o detalles)"}), 400

        # Calcular total y armar detalle
        total = 0
        detalles_pedido = []
        # items_mp = []

        for item in detalles:
            producto = Producto.query.get(item["producto_id"])
            if not producto:
                return jsonify({"error": f"Producto id {item['producto_id']} no encontrado"}), 404

            if item.get("cantidad") > producto.stock:
                return jsonify({"error": f"Stock insuficiente para producto id {item['producto_id']}"}), 400
            
            producto.stock -= item.get("cantidad", 1)  # Reducir stock
            cantidad = item.get("cantidad", 1)
            subtotal = producto.precio * cantidad
            total += subtotal

            detalles_pedido.append(
                PedidoDetalle(
                    producto_id=producto.id,
                    cantidad=cantidad,
                    subtotal=subtotal
                )
            )

            # # Armar ítem para Mercado Pago
            # items_mp.append({
            #     "id": str(producto.id),
            #     "title": producto.nombre,
            #     "quantity": cantidad,
            #     "unit_price": float(producto.precio),
            #     "currency_id": "ARS"
            # })

        # Crear pedido en estado PENDIENTE
        pedido = Pedido(usuario_id=usuario_id, total=total, estado="PENDIENTE", detalles=detalles_pedido)
        db.session.add(pedido)
        db.session.commit()  # para tener el pedido_id generado

        # # Crear preferencia en Mercado Pago
        # preference_data = {
        #     "items": items_mp,
        #     "back_urls": {
        #         "success": f"http://localhost:3000/pagos/success",
        #         "failure": f"http://localhost:3000/pagos/failure",
        #         "pending": f"http://localhost:3000/pagos/pending"
        #     },
        #     "auto_return": None,
        #     "external_reference": str(pedido.id),
        #     "notification_url": "http://localhost:5000/api/pagos/notificacion"
        # }

        # preference_response = sdk.preference().create(preference_data)
        # print(preference_response)
        # preference = preference_response["response"]

        # return jsonify({
        #     "pedido_id": pedido.id,
        #     "total": total,
        #     "estado": pedido.estado,
        #     "init_point": preference["init_point"],
        #     "sandbox_init_point": preference["sandbox_init_point"]
        # }), 201
        return jsonify({
            "pedido_id": pedido.id,
            "total": total,
            "estado": pedido.estado
        }), 201

    except Exception as e:
        print(str(e))
        return jsonify({"error": str(e)}), 500

# Ver detalle de un pedido
@pedidos_bp.route("/unico/<int:id>", methods=["GET"])
def detalle_pedido(id):
    pedido = Pedido.query.get(id)
    if not pedido:
        return jsonify({"error": "Pedido no encontrado"}), 404

    return jsonify({
        "id": pedido.id,
        "estado": pedido.estado,
        "total": pedido.total,
        "fecha_creacion": pedido.fecha_creacion.isoformat(),
        "detalles": [
            {
                "producto": i.producto.nombre,
                "cantidad": i.cantidad,
                "precio_unitario": i.precio_unitario,
                "subtotal": i.subtotal
            } for i in pedido.detalles
        ]
    })

# Actualizar estado del pedido (solo admin para cambiar a ENVIADO o ENTREGADO)
@pedidos_bp.route("/<int:id>", methods=["PATCH"])
def actualizar_pedido(id):
    current = get_jwt_identity()
    data = request.get_json() or {}
    pedido = Pedido.query.get_or_404(id)

    # Solo admin puede cambiar estado
    if "estado" in data:
        if current.get("rol") != "ADMIN":
            return jsonify({"error": "Acceso denegado"}), 403
        pedido.estado = data["estado"]

    db.session.commit()
    return jsonify({"message": "Pedido actualizado", "estado": pedido.estado})

# @pedidos_bp.route("/notificacion", methods=["POST"])
# def notificacion():
#     try:
#         data = request.get_json()

#         if not data or "id" not in data or "topic" not in data:
#             return jsonify({"error": "Notificación inválida"}), 400

#         # Procesamos solo notificaciones de pagos
#         if data["topic"] == "payment":
#             payment_response = sdk.payment().get(data["id"])
#             pago_info = payment_response["response"]

#             pedido_id = pago_info.get("external_reference")
#             estado_pago = pago_info.get("status")  # approved, pending, rejected
#             detalle_estado = pago_info.get("status_detail")

#             # Buscamos el pedido en la DB
#             pedido = Pedido.query.get(int(pedido_id)) if pedido_id else None
#             if not pedido:
#                 return jsonify({"error": "Pedido no encontrado"}), 404

#             # Mapeamos estado de MP a estado de pedido
#             if estado_pago == "approved":
#                 pedido.estado = "APROBADO"
#             elif estado_pago == "pending":
#                 pedido.estado = "PENDIENTE"
#             elif estado_pago == "rejected":
#                 pedido.estado = "RECHAZADO"
#             else:
#                 pedido.estado = "DESCONOCIDO"

#             db.session.commit()

#             return jsonify({
#                 "message": "Pedido actualizado",
#                 "pedido_id": pedido.id,
#                 "estado": pedido.estado,
#                 "detalle_estado": detalle_estado
#             }), 200

#         return jsonify({"message": "Evento ignorado"}), 200

#     except Exception as e:
#         return jsonify({"error": str(e)}), 500
        
