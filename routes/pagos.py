from database import db
import os
import mercadopago
from flask import Blueprint, request, jsonify
from models import Pedido, Pago, Usuario, Producto
from services.notifications import (
    send_user_payment_approved,
    send_user_payment_rejected,
    send_admin_payment_approved,
    send_user_transfer_instructions
)

pagos_bp = Blueprint("pagos", __name__, url_prefix="/api/pagos")
sdk = mercadopago.SDK(str(os.getenv("MP_ACCESS_TOKEN")))

@pagos_bp.route("/webhook", methods=["POST", "GET"])
def webhook_mp():
    try:
        data = request.get_json(silent=True) or {}

        # soporta payment.created / payment.updated y también "payment"
        event_type = data.get("type")
        action = data.get("action")

        payment_id = None
        if isinstance(data.get("data"), dict):
            payment_id = data["data"].get("id")

        # logs para ver qué llega
        print("MP WEBHOOK:", {"action": action, "type": event_type, "payment_id": payment_id})

        if event_type != "payment" or not payment_id:
            return jsonify({"status": "ignored"}), 200

        pago_info = sdk.payment().get(payment_id)
        pago = (pago_info or {}).get("response") or {}
        if not pago:
            print("MP SDK sin response:", pago_info)
            return jsonify({"status": "no_response"}), 200

        referencia = pago.get("external_reference")
        if not referencia:
            return jsonify({"status": "no_external_reference"}), 200

        pago_reg = Pago.query.get(int(referencia))
        if not pago_reg:
            return jsonify({"status": "pago_not_found"}), 200

        # idempotencia
        if pago_reg.id_pago_mp == str(payment_id):
            return jsonify({"status": "ok"}), 200

        pedido = Pedido.query.get(pago_reg.pedido_id)
        if not pedido:
            return jsonify({"status": "pedido_not_found"}), 200
        
        previous_estado = pago_reg.estado #guardar para el mail
        
        estado = pago.get("status")
        pago_reg.id_pago_mp = str(payment_id)
        pago_reg.estado = estado
        pago_reg.detalle_estado = pago.get("status_detail")
        pago_reg.monto = pago.get("transaction_amount")
        pago_reg.metodo_pago = (pago.get("payment_method") or {}).get("id")
        pago_reg.tipo_pago = pago.get("payment_type_id")
        pago_reg.id_orden_mercante = str((pago.get("order") or {}).get("id"))

        if estado == "approved":
            if pedido.estado == "EXPIRADO":
                # pago aprobado pero pedido vencido → revisión manual
                pedido.estado = "REVISAR"   # o "PAGO_TARDE"
            else:
                pedido.estado = "PAGADO"
                pedido.stock_state = "confirmed"
                pedido.expires_at = None

        elif estado in ("pending", "in_process", "in_mediation"):
            # Ojo: acá vos estabas usando "PENDIENTE" pero tu sistema usa "PENDIENTE_PAGO"
            pedido.estado = "PENDIENTE_PAGO"

        elif estado == "rejected":
            pedido.estado = "RECHAZADO"
        else:
            pedido.estado = "PENDIENTE_PAGO"

              
        db.session.commit()
        
        # ✅ Envío de mails solo si cambió el estado
        if estado != previous_estado:
            usuario = Usuario.query.get(pedido.usuario_id)

            if estado == "approved":
                # Usuario
                if usuario and (pago_reg.ultimo_estado_notificado != "approved"):
                    send_user_payment_approved(usuario, pedido, pago_reg)

                # Admin
                if usuario and not pago_reg.notificado_admin:
                    send_admin_payment_approved(pedido, pago_reg, usuario)

                pago_reg.ultimo_estado_notificado = "approved"
                pago_reg.notificado_user = True
                pago_reg.notificado_admin = True
                db.session.commit()

            elif estado == "rejected":
                if usuario and (pago_reg.ultimo_estado_notificado != "rejected"):
                    send_user_payment_rejected(usuario, pedido, pago_reg)

                pago_reg.ultimo_estado_notificado = "rejected"
                pago_reg.notificado_user = True
                db.session.commit()
                
        return jsonify({"status": "ok"}), 200
    
    except Exception as e:
        # IMPORTANTÍSIMO: no tires 500 si querés evitar reintentos infinitos por algo que es tu bug
        print("ERROR WEBHOOK:", repr(e))
        return jsonify({"status": "error_logged"}), 200


@pagos_bp.route("/preferencia", methods=["POST"])
def crear_preferencia_pago():
    try:
        data = request.get_json() or {}

        pedido_id = data.get("pedido_id")
        tipo_pago = data.get("tipo_pago")  # debito | credito | mercadopago | transferencia

        pedido = Pedido.query.get(pedido_id)
        if not pedido:
            return jsonify({"error": "Pedido no encontrado"}), 404

        detalles = pedido.detalles  
        costo_envio = float(pedido.costo_envio or 0)

        if not detalles:
            return jsonify({"error": "El pedido no tiene items"}), 400

        # =====================================================
        # 0) Si el pago es por transferencia → NO usar Mercado Pago
        # =====================================================
        if tipo_pago == "transferencia":
            pago = Pago(
                pedido_id=pedido_id,
                referencia_externa=str(pedido_id),
                estado="pendiente",
                detalle_estado="awaiting_transfer",
                metodo_pago="transferencia",
                tipo_pago="bank_transfer",
                monto=pedido.total,
            )
            db.session.add(pago)
            db.session.commit()
            
            instrucciones = {
                "alias": "TU_ALIAS",
                "cbu": "TU_CBU",
                "titular": "TU_TITULAR",
                "cuit": "TU_CUIT",
                "concepto": f"PEDIDO {pedido_id}"
            }
            
            usuario = Usuario.query.get(pedido.usuario_id)
            if usuario:
                send_user_transfer_instructions(usuario, pedido, pago, instrucciones)
            return jsonify({
                "mensaje": "Transferencia registrada",
                "pedido_id": pedido_id,
                "monto": pedido.total,
                "referencia": str(pedido_id),
                "instrucciones": instrucciones
            }), 201

        # =====================================================
        # 1) Armamos items Mercado Pago
        # =====================================================
        mp_items = []
        total = 0.0

        for d in detalles:
            prod = d.producto  # <-- gracias al backref
            if not prod:
                return jsonify({"error": f"Producto no encontrado: {d.producto_id}"}), 404

            unit_price = float(prod.precio)  # o subtotal/cantidad, pero mejor usar precio real
            qty = int(d.cantidad)

            mp_items.append({
                "id": str(prod.id),
                "title": prod.nombre,
                "quantity": qty,
                "unit_price": unit_price,
                "currency_id": "ARS"
            })

            total += unit_price * qty

        # =====================================================
        # 2) Costo de envio y recargo por credito
        # =====================================================
        if costo_envio > 0:
            total += costo_envio
            mp_items.append({
                "id": "envio",
                "title": "Costo de envío",
                "quantity": 1,
                "unit_price": float(costo_envio),
                "currency_id": "ARS"
            })

        # crédito +10%
        if tipo_pago == "credito":
            total = round(total * 1.10, 2)
            for it in mp_items:
                it["unit_price"] = round(float(it["unit_price"]) * 1.10, 2)
                
        # =====================================================
        # 3) Restricciones según tipo pago
        # =====================================================
        payment_rules = build_payment_restrictions(tipo_pago)

        # =====================================================
        # 4) Guardar pago
        # =====================================================
        pago_mp = Pago(
            pedido_id=pedido_id,
            id_preferencia=None,
            url_checkout=None,
            referencia_externa=None, 
            estado="pendiente",
            metodo_pago=tipo_pago,
            monto=total
        )

        db.session.add(pago_mp)
        db.session.commit()
        
        # =====================================================
        # 5) Crear preferencia
        # =====================================================
        preference_data = {
            "items": mp_items,
            "external_reference": str(pago_mp.id), 
            "back_urls": {
                "success": f"https://loversplay-six.vercel.app/pagos?status=success&pedido_id={pedido_id}",
                "failure": "https://loversplay-six.vercel.app/pagos?status=failure",
                "pending": f"https://loversplay-six.vercel.app/pagos?status=pending&pedido_id={pedido_id}"
            },
            "auto_return": "approved",
            "notification_url": os.getenv("MP_NOTIFICATION_URL"),
            "binary_mode": True
        }
        

        # Agregar reglas de pagos SOLO si existen
        if payment_rules is not None:
            preference_data["payment_methods"] = payment_rules
        
        
        pref_info = sdk.preference().create(preference_data)
        pref = pref_info.get("response", {})
        
        pref_id = pref["id"]
        check = sdk.preference().get(pref_id)
        print("PREFERENCE STORED:", check.get("response", {}).get("notification_url"))

        if "id" not in pref:
            raise Exception(f"MercadoPago Error: {pref_info}")

        if "id" not in pref:
            raise Exception(f"MercadoPago Error: {pref}")

        # =====================================================
        # 6) Actualizar el mismo Pago con la preferencia
        # =====================================================
        pago_mp.id_preferencia = pref["id"]
        pago_mp.url_checkout = pref["init_point"]
        pago_mp.referencia_externa = str(pago_mp.id)  # opcional
        db.session.commit()

        return jsonify({
            "preference_id": pref["id"],
            "init_point": pref["init_point"],
            "pedido_id": pedido_id,
            "pago_id": pago_mp.id
        }), 201


    except Exception as e:
        print("ERROR MP:", e)
        return jsonify({"error": str(e)}), 500

def build_payment_restrictions(tipo_pago):

    # Plantilla base requerida por Mercado Pago
    rules = {
        "excluded_payment_types": [],
        "excluded_payment_methods": []
    }

    if tipo_pago == "debito":
        rules["excluded_payment_types"] = [
            {"id": "credit_card"},
            {"id": "ticket"},
            {"id": "bank_transfer"},
            {"id": "atm"},
            {"id": "digital_wallet"},
            {"id": "prepaid_card"}
        ]
        return rules

    if tipo_pago == "credito":
        rules["excluded_payment_types"] = [
            {"id": "debit_card"},
            {"id": "ticket"},
            {"id": "bank_transfer"},
            {"id": "atm"},
            {"id": "digital_wallet"},
            {"id": "prepaid_card"}
        ]
        return rules

    if tipo_pago == "mercadopago":
        rules["excluded_payment_types"] = [
            {"id": "credit_card"},
            {"id": "debit_card"},
            {"id": "ticket"},
            {"id": "bank_transfer"},
            {"id": "atm"},
            {"id": "prepaid_card"}
        ]
        return rules

    if tipo_pago == "transferencia":
        return None

    # Si permite todo → retornar reglas vacías PERO válidas
    return rules
