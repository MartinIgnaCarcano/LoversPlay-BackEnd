import os
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
from models import db, Categoria, Producto
from sqlalchemy import func

categorias_bp = Blueprint("categorias", __name__, url_prefix="/api/categorias")

UPLOAD_FOLDER = "static/imagenes/categorias"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def nombreArchivoFinal(filename, nombre, id):
    return str(id) + "_" + nombre + "." + filename.rsplit('.', 1)[1].lower()

# Crear categoría
@categorias_bp.route("/", methods=["POST"])
def crear_categoria():
    nombre = request.form.get("nombre")
    if not nombre:
        return jsonify({"msg": "Falta nombre"}), 400

    categoria = Categoria(nombre=nombre)
    
    db.session.add(categoria)
    db.session.flush()  
    # Imagen
    if "imagen" in request.files:
        file = request.files["imagen"]
        if file and allowed_file(file.filename):
            filename = secure_filename(nombreArchivoFinal(file.filename, nombre, categoria.id))
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filepath)
            categoria.url_imagen = f"/{filepath}"

    db.session.commit()
    return jsonify({"id": categoria.id, "nombre": categoria.nombre, "url_imagen": categoria.url_imagen}), 201

@categorias_bp.route("/", methods=["GET"])
def listar_categorias():
    categorias = (
        db.session.query(
            Categoria.id,
            Categoria.nombre,
            Categoria.url_imagen,
            func.count(Producto.id).label("cantidad_productos")
        )
        .outerjoin(Producto, Categoria.id == Producto.categoria_id)
        .group_by(Categoria.id)
        .order_by(func.count(Producto.id).desc())  # 🔽 de mayor a menor
        .all()
    )

    data = [
        {
            "id": c.id,
            "nombre": c.nombre,
            "url_imagen": c.url_imagen,
            "cantidad_productos": c.cantidad_productos
        }
        for c in categorias
    ]

    return jsonify(data)

# Obtener una categoría
@categorias_bp.route("/<int:id>", methods=["GET"])
def detalle_categoria(id):
    c = Categoria.query.get_or_404(id)
    return jsonify({"id": c.id, "nombre": c.nombre, "url_imagen": c.url_imagen, "slug": c.slug})

# Actualizar categoría
@categorias_bp.route("/<int:id>", methods=["PUT", "PATCH"])
def actualizar_categoria(id):
    c = Categoria.query.get_or_404(id)
    nombre = request.form.get("nombre")
    if nombre:
        c.nombre = nombre

    if "imagen" in request.files:
        file = request.files["imagen"]
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filepath)
            c.url_imagen = f"/{filepath}"

    db.session.commit()
    return jsonify({"msg": "Categoría actualizada", "id": c.id, "nombre": c.nombre, "url_imagen": c.url_imagen})

#Eliminar categoría
@categorias_bp.route("/<int:id>", methods=["DELETE"])
def eliminar_categoria(id):
    c = Categoria.query.get_or_404(id)
    
    # Eliminar imagen del filesystem si existe
    if c.url_imagen:
        # La url en DB es algo como "/static/imagenes/categorias/imagen.jpg"
        # Convertimos a path absoluto
        imagen_path = c.url_imagen.lstrip("/")  # quitar la barra inicial
        if os.path.exists(imagen_path):
            try:
                os.remove(imagen_path)
            except Exception as e:
                print(f"No se pudo eliminar la imagen: {e}")
    
    db.session.delete(c)
    db.session.commit()
    return jsonify({"msg": "Categoría eliminada"})

