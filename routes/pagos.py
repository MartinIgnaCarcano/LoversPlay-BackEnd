from database import db
import os
import mercadopago
from flask import Blueprint, request, jsonify
from models import Pedido, Pago
import requests

pagos_bp = Blueprint("pagos", __name__, url_prefix="/api/pagos")
sdk = mercadopago.SDK("APP_USR-8996751005930022-112715-9268db70d5e2dc631505b74a818b8481-2611950632")

@pagos_bp.route("/webhook", methods=["POST"])
def webhook_mp():
    try:
        data = request.get_json()

        tipo = data.get("type")
        if tipo != "payment":
            return jsonify({"status": "ignored"}), 200

        payment_id = data["data"]["id"]

        # =====================================================
        # 1) Consultar API de Mercado Pago para obtener datos reales
        # =====================================================
        pago_info = sdk.payment().get(payment_id)
        pago = pago_info["response"]


        estado = pago.get("status")           # approved / pending / rejected
        detalle_estado = pago.get("status_detail")
        monto = pago.get("transaction_amount")
        metodo = pago.get("payment_method", {}).get("id")
        tipo_pago = pago.get("payment_type_id")
        orden_mercante = pago.get("order", {}).get("id")
        referencia = pago.get("external_reference")

        if not referencia:
            print("SIN referencia externa. Ignorando...")
            return jsonify({"status": "no external_reference"}), 200

        pedido_id = int(referencia)

        # =====================================================
        # 2) Buscar Pedido en BD
        # =====================================================
        pedido = Pedido.query.get(pedido_id)
        if not pedido:
            print("PEDIDO NO ENCONTRADO")
            return jsonify({"error": "Pedido no encontrado"}), 404

        # =====================================================
        # 3) Crear o actualizar Pago en tu BD
        # =====================================================
        pago_reg = Pago.query.filter_by(id_pago_mp=str(payment_id)).first()

        if not pago_reg:
            pago_reg = Pago(
                pedido_id=pedido_id,
                id_preferencia=None,
                url_checkout=None,
                referencia_externa=str(pedido_id),
                id_pago_mp=str(payment_id),
                id_orden_mercante=str(orden_mercante),
                estado=estado,
                detalle_estado=detalle_estado,
                metodo_pago=metodo,
                tipo_pago=tipo_pago,
                monto=monto,
            )
            db.session.add(pago_reg)
        else:
            # Actualizar
            pago_reg.estado = estado
            pago_reg.detalle_estado = detalle_estado
            pago_reg.metodo_pago = metodo
            pago_reg.tipo_pago = tipo_pago
            pago_reg.monto = monto

        # =====================================================
        # 4) Actualizar estado del Pedido
        # =====================================================
        if estado == "approved":
            pedido.estado = "PAGADO"
        elif estado == "pending":
            pedido.estado = "PENDIENTE"
        else:
            pedido.estado = "RECHAZADO"

        db.session.commit()

        print("=== PEDIDO ACTUALIZADO CORRECTAMENTE ===")
        return jsonify({"status": "ok"}), 200

    except Exception as e:
        print("ERROR WEBHOOK:", e)
        return jsonify({"error": str(e)}), 500

@pagos_bp.route("/preferencia", methods=["POST"])
def crear_preferencia_pago():
    try:
        data = request.get_json() or {}

        pedido_id = data.get("pedido_id")
        items = data.get("items")
        costo_envio = data.get("costo_envio", 0)
        tipo_pago = data.get("tipo_pago")  # debito | credito | mercadopago | transferencia

        if not pedido_id or not items or not tipo_pago:
            return jsonify({"error": "Faltan datos para crear la preferencia"}), 400

        # =====================================================
        # 0) Si el pago es por transferencia → NO usar Mercado Pago
        # =====================================================
        if tipo_pago == "transferencia":
            pago = Pago(
                pedido_id=pedido_id,
                id_preferencia=None,
                url_checkout=None,
                referencia_externa=str(pedido_id),
                estado="pendiente",
                metodo_pago="transferencia",
                tipo_pago="bank_transfer",
                monto=sum(i["precio"] * i["cantidad"] for i in items) + costo_envio
            )
            db.session.add(pago)
            db.session.commit()

            return jsonify({
                "mensaje": "Pago por transferencia registrado como pendiente",
                "pedido_id": pedido_id
            }), 201

        # =====================================================
        # 1) Armamos items Mercado Pago
        # =====================================================
        mp_items = []
        total = 0

        for item in items:
            subtotal = item["precio"] * item["cantidad"]
            total += subtotal

            mp_items.append({
                "id": str(item["producto_id"]),
                "title": item["nombre"],
                "quantity": item["cantidad"],
                "unit_price": float(item["precio"]),
                "currency_id": "ARS"
            })

        # Agregar costo de envío
        if costo_envio > 0:
            total += costo_envio
            mp_items.append({
                "id": "envio",
                "title": "Costo de envío",
                "quantity": 1,
                "unit_price": float(costo_envio),
                "currency_id": "ARS"
            })

        # =====================================================
        # 2) Si es crédito aplicamos +10%
        # =====================================================
        if tipo_pago == "credito":
            total *= 1.10  # recargo
            for item in mp_items:
                item["unit_price"] = round(item["unit_price"] * 1.10, 2)

        # =====================================================
        # 3) Restricciones según tipo pago
        # =====================================================
        payment_rules = build_payment_restrictions(tipo_pago)

        # =====================================================
        # 4) Crear preferencia
        # =====================================================
        preference_data = {
            "items": mp_items,
            "external_reference": str(pedido_id),
            "back_urls": {
                "success": "https://loversplay-six.vercel.app/pagos/success",
                "failure": "https://loversplay-six.vercel.app/pagos/failure",
                "pending": "https://loversplay-six.vercel.app/pagos/pending"
            },
            "auto_return": "approved",
            "notification_url": "https://mckenzie-burthensome-denita.ngrok-free.dev/api/pagos/webhook"
        }

        # Agregar reglas de pagos SOLO si existen
        if payment_rules is not None:
            preference_data["payment_methods"] = payment_rules
        
        
        MP_ACCESS_TOKEN = "APP_USR-8996751005930022-112715-9268db70d5e2dc631505b74a818b8481-2611950632"

        res = requests.post(
            "https://api.mercadopago.com/checkout/preferences",
            headers={
                "Authorization": f"Bearer {MP_ACCESS_TOKEN}",
                "Content-Type": "application/json"
            },
            json=preference_data
        )

        pref = res.json()

        if "id" not in pref:
            raise Exception(f"MercadoPago Error: {pref}")
        
        # =====================================================
        # 5) Guardar pago
        # =====================================================
        pago = Pago(
            pedido_id=pedido_id,
            id_preferencia=pref["id"],
            url_checkout=pref["init_point"],
            referencia_externa=str(pedido_id),
            estado="pendiente",
            metodo_pago=tipo_pago,
            monto=total
        )

        db.session.add(pago)
        db.session.commit()

        return jsonify({
            "preference_id": pref["id"],
            "init_point": pref["init_point"],
            "pedido_id": pedido_id
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
