import os
import mercadopago
from flask import Blueprint, request, jsonify

pagos_bp = Blueprint("pagos", __name__, url_prefix="/api/pagos")

sdk = mercadopago.SDK("APP_USR-6608167090676875-091814-964957d986e21eee913f06709c51abeb-2611950632")

