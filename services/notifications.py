# services/notifications.py
import os
from flask import current_app
from models import Usuario, Pedido, Pago

from services.email_service import send_email  # tu función que ya funciona

def _admin_email():
    return current_app.config.get("ADMIN_EMAIL") or os.getenv("ADMIN_EMAIL")

def _safe_send(to, subject, html):
    if not to:
        print("EMAIL: destinatario vacío, se ignora:", subject)
        return
    try:
        send_email(to=to, subject=subject, html=html)
    except Exception as e:
        # IMPORTANTÍSIMO: que no rompa la request
        print("EMAIL ERROR:", subject, repr(e))

def send_user_welcome(usuario: Usuario):
    html = f"""
    <h2>¡Bienvenido/a a Lovers Play, {usuario.nombre or ""}! 🎉</h2>
    <p>Tu cuenta fue creada con éxito con el email: <b>{usuario.email}</b>.</p>
    <p>Ya podés hacer compras y seguir tus pedidos desde tu perfil.</p>
    """
    _safe_send(usuario.email, "Bienvenido/a a Lovers Play 🎉", html)

def send_user_order_created(usuario: Usuario, pedido: Pedido):
    html = f"""
    <h2>Pedido #{pedido.id} creado ✅</h2>
    <p>Recibimos tu pedido. Estado: <b>{pedido.estado}</b></p>
    <p>Total: <b>${pedido.total:.2f}</b></p>
    <p>Te avisaremos cuando haya novedades.</p>
    """
    _safe_send(usuario.email, f"Tu pedido #{pedido.id} fue creado ✅", html)

def send_admin_new_order(pedido: Pedido, usuario: Usuario | None):
    admin = _admin_email()
    u = usuario.email if usuario else "desconocido"
    html = f"""
    <h2>Nuevo pedido #{pedido.id} 🛒</h2>
    <p>Usuario: <b>{u}</b></p>
    <p>Total: <b>${pedido.total:.2f}</b></p>
    <p>Estado: <b>{pedido.estado}</b></p>
    """
    _safe_send(admin, f"Nuevo pedido #{pedido.id} 🛒", html)

def send_user_payment_approved(usuario: Usuario, pedido: Pedido, pago: Pago):
    html = f"""
    <h2>Pago aprobado ✅</h2>
    <p>Tu pago del pedido <b>#{pedido.id}</b> fue aprobado.</p>
    <p>Monto: <b>${pago.monto:.2f}</b></p>
    <p>¡Gracias por tu compra!</p>
    """
    _safe_send(usuario.email, f"Pago aprobado - Pedido #{pedido.id} ✅", html)

def send_admin_payment_approved(pedido: Pedido, pago: Pago, usuario: Usuario | None):
    admin = _admin_email()
    u = usuario.email if usuario else "desconocido"
    html = f"""
    <h2>Pago aprobado ✅</h2>
    <p>Pedido: <b>#{pedido.id}</b></p>
    <p>Usuario: <b>{u}</b></p>
    <p>Monto: <b>${pago.monto:.2f}</b></p>
    <p>Método: <b>{pago.metodo_pago}</b></p>
    """
    _safe_send(admin, f"Pago aprobado - Pedido #{pedido.id} ✅", html)

def send_user_payment_rejected(usuario: Usuario, pedido: Pedido, pago: Pago):
    detail = pago.detalle_estado or ""
    html = f"""
    <h2>Pago rechazado ❌</h2>
    <p>El pago del pedido <b>#{pedido.id}</b> fue rechazado.</p>
    <p>Detalle: <b>{detail}</b></p>
    <p>Podés reintentar el pago desde tu perfil o elegir otro método.</p>
    """
    _safe_send(usuario.email, f"Pago rechazado - Pedido #{pedido.id} ❌", html)

def send_user_transfer_instructions(usuario: Usuario, pedido: Pedido, pago: Pago, instrucciones: dict):
    html = f"""
    <h2>Transferencia registrada 🏦</h2>
    <p>Pedido: <b>#{pedido.id}</b></p>
    <p>Monto: <b>${pago.monto:.2f}</b></p>
    <p><b>Alias:</b> {instrucciones.get("alias")}</p>
    <p><b>CBU:</b> {instrucciones.get("cbu")}</p>
    <p><b>Titular:</b> {instrucciones.get("titular")}</p>
    <p><b>Concepto:</b> {instrucciones.get("concepto")}</p>
    <p>Cuando envíes la transferencia, marcala como "enviada" (o adjuntá comprobante) para que podamos verificarla.</p>
    """
    _safe_send(usuario.email, f"Instrucciones de transferencia - Pedido #{pedido.id}", html)

def send_user_transfer_sent(usuario: Usuario, pedido: Pedido):
    html = f"""
    <h2>Transferencia informada ✅</h2>
    <p>Recibimos tu aviso de transferencia del pedido <b>#{pedido.id}</b>.</p>
    <p>Ahora vamos a verificarla y te avisaremos cuando el pedido cambie de estado.</p>
    """
    _safe_send(usuario.email, f"Transferencia enviada - Pedido #{pedido.id} ✅", html)

def send_admin_transfer_sent(pedido: Pedido, usuario: Usuario | None):
    admin = _admin_email()
    u = usuario.email if usuario else "desconocido"
    html = f"""
    <h2>Transferencia informada 🧾</h2>
    <p>Pedido: <b>#{pedido.id}</b></p>
    <p>Usuario: <b>{u}</b></p>
    <p>Revisar comprobante/confirmación.</p>
    """
    _safe_send(admin, f"Transferencia informada - Pedido #{pedido.id}", html)
