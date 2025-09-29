import os
import mercadopago
from flask import Blueprint, request, jsonify

pagos_bp = Blueprint("pagos", __name__, url_prefix="/api/pagos")

sdk = mercadopago.SDK("")

