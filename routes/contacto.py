from flask import Blueprint, request, jsonify
from services.email_service import send_email  # ajustá el import según tu estructura

contact_bp = Blueprint("contact", __name__)

@contact_bp.route("/api/contact", methods=["POST"])
def contact():
    data = request.get_json()

    name = data.get("name")
    email = data.get("email")
    phone = data.get("phone", "-")
    subject = data.get("subject")
    message = data.get("message")

    html = f"""
        <h2>Nuevo mensaje de contacto desde la Pagina Web</h2>
        <p><strong>Nombre:</strong> {name}</p>
        <p><strong>Email:</strong> {email}</p>
        <p><strong>Teléfono:</strong> {phone}</p>
        <p><strong>Asunto:</strong> {subject}</p>
        <p><strong>Mensaje:</strong></p>
        <p>{message}</p>
    """

    try:
        send_email(
            to="loversplay.soporte@gmail.com",
            subject=f"Contacto web: {subject}",
            html=html,
            reply_to=email
        )
        return jsonify({"ok": True}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500