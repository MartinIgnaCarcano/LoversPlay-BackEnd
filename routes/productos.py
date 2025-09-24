import os
from flask import Blueprint, json, request, jsonify
from models import ImagenProducto, Producto, Categoria
from werkzeug.utils import secure_filename
from database import db
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import desc

productos_bp = Blueprint("productos", __name__, url_prefix="/api/productos")

UPLOAD_FOLDER = "static/imagenes/productos"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def nombreArchivoFinal(filename, nombre, id, indice):
    return str(id) + "_" + nombre + "_" + str(indice) + "." + filename.rsplit('.', 1)[1].lower()

def fix_encoding(texto: str) -> str:
    if not texto:
        return texto
    reemplazos = {
        "├¡": "í", "├í": "í", "Ã­": "í",
        "├®": "é", "Ã©": "é",
        "├│": "ó", "Ã³": "ó",
        "├║": "ú", "Ãº": "ú",
        "Ã¡": "á", "├í": "á",
        "Ã±": "ñ",
        "┬á": " ",
        "┬": ""
    }
    for roto, bien in reemplazos.items():
        texto = texto.replace(roto, bien)
    return texto


@productos_bp.route("/por_categoria", methods=["GET"])
def listar_productos():
    try:
        # Leer categorías de la query (?ids=1,2,3)
        ids_param = request.args.get("ids")
        if not ids_param:
            return jsonify({"msg": "Debe indicar al menos una categoría"}), 400

        categoria_ids = [int(cid) for cid in ids_param.split(",") if cid.isdigit()]

        if not categoria_ids:
            return jsonify({"msg": "IDs de categoría inválidos"}), 400

        # Paginación
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 10))
        offset_value = (page - 1) * per_page

        # Query con múltiples categorías
        productos = (
            Producto.query
            .filter(Producto.categoria_id.in_(categoria_ids))
            .order_by(desc(Producto.vistas * 0.7 + Producto.valoracion_promedio * 0.3))
            .limit(per_page)
            .offset(offset_value)
            .all()
        )

        # Total para saber cuántos productos hay
        total = Producto.query.filter(Producto.categoria_id.in_(categoria_ids)).count()

        return jsonify({
            "page": page,
            "per_page": per_page,
            "total": total,
            "productos": [
                {
                    "id": p.id,
                    "nombre": p.nombre,
                    "precio": p.precio,
                    "url_imagen_principal": p.url_imagen_principal,
                    "stock": p.stock,
                    "vistas": p.vistas,
                    "valoracion_promedio": p.valoracion_promedio,
                }
                for p in productos
            ]
        })
    except Exception as e:
        return jsonify({"msg": "Error al listar productos", "error": str(e)}), 500

# Detalle de un producto
@productos_bp.route("/<int:id>", methods=["GET"])
def detalle_producto(id):
    try:
        p = Producto.query.get(id)
        if not p:
            return jsonify({"msg": "Producto no encontrado"}), 404
        p.vistas += 1
        db.session.commit()
        # --- Obtener sugerencias ---
        sugeridos = (
            Producto.query
            .filter(Producto.categoria_id == p.categoria_id, Producto.id != p.id)
            .order_by(Producto.vistas.desc(), Producto.valoracion_promedio.desc())
            .limit(3)  # Ej: máximo 3 sugeridos
            .all()
        )

        sugeridos_data = [
            {
                "id": s.id,
                "nombre": s.nombre,
                "precio": s.precio,
                "url_imagen_principal": s.url_imagen_principal
            }
            for s in sugeridos
        ]

        return jsonify({
            "id": p.id,
            "nombre": p.nombre,
            "precio": p.precio,
            "peso": p.peso,
            "stock": p.stock,
            "url_imagen_principal": p.url_imagen_principal,
            "categoria_id": p.categoria_id,
            "slug": p.slug,
            "descripcion_corta": p.descripcion_corta,
            "descripcion_larga": p.descripcion_larga,
            "imagenes": [img.url_imagen for img in p.imagenes],
            "sugeridos": sugeridos_data
        })
    except Exception as e:
        return jsonify({"msg": "Error interno", "error": str(e)}), 500

@productos_bp.route("/", methods=["GET"])
def listar_todos_productos():
    try:
        # Parámetros de query (?page=2&per_page=10)
        page = int(request.args.get("page", 1))       # Página actual (default 1)
        per_page = int(request.args.get("per_page", 10))  # Productos por página (default 10)

        # Calcular desde dónde empezar
        offset_value = (page - 1) * per_page

        # Query con orden por relevancia
        productos = (
            Producto.query
            .order_by(desc(Producto.vistas * 0.7 + Producto.valoracion_promedio * 0.3))
            .limit(per_page)
            .offset(offset_value)
            .all()
        )

        # Total de productos (para que el frontend sepa cuándo cortar)
        total = Producto.query.count()

        return jsonify({
            "page": page,
            "per_page": per_page,
            "total": total,
            "productos": [
                {
                    "id": p.id,
                    "nombre": p.nombre,
                    "precio": p.precio,
                    "url_imagen_principal": p.url_imagen_principal,
                    "stock": p.stock,
                    "vistas": p.vistas,
                    "valoracion_promedio": p.valoracion_promedio,
                }
                for p in productos
            ]
        })
    except Exception as e:
        return jsonify({"msg": "Error al listar productos", "error": str(e)}), 500

# Crear producto 
@productos_bp.route("/", methods=["POST"])
def crear_producto():
    # Datos del formulario
    nombre = request.form.get("nombre")
    descripcion_corta = request.form.get("descripcion_corta")
    descripcion_larga = request.form.get("descripcion_larga")
    precio = request.form.get("precio", type=float)
    stock = request.form.get("stock", type=int, default=0)
    peso = request.form.get("peso")
    categoria_id = request.form.get("categoria_id", type=int)
    slug = request.form.get("slug")
    
    producto = Producto(
        nombre=nombre,
        descripcion_corta=descripcion_corta,
        descripcion_larga=descripcion_larga,
        precio=precio,
        stock=stock,
        peso=peso,
        categoria_id=categoria_id,
        slug=slug,
        vistas=0,
        valoracion_promedio=0.0,
    )

    db.session.add(producto)
    db.session.flush()  # Genera el id del producto sin hacer commit

    if "imagen_principal" in request.files:
        file = request.files["imagen_principal"]
        if file and allowed_file(file.filename):
            filename = secure_filename(nombreArchivoFinal(file.filename, producto.nombre, producto.id, "principal"))
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filepath)
            producto.url_imagen_principal = f"/{filepath}"
        else:
            return jsonify({"msg": "Archivo de imagen principal no permitido"}), 400
    # Archivos
    if "imagenes" in request.files:
        files = request.files.getlist("imagenes")
        for i, file in enumerate(files):
            if file and allowed_file(file.filename):
                filename = secure_filename(nombreArchivoFinal(file.filename, producto.nombre, producto.id, i))
                filepath = os.path.join(UPLOAD_FOLDER, filename)
                file.save(filepath)
                producto.imagenes.append(ImagenProducto(url_imagen=f"/{filepath}"))
            else:
                return jsonify({"msg": "Archivo de imagen no permitido"}), 400

    # Características
    if caracteristicas := request.files.get("caracteristicas"):
        try:
            producto.caracteristicas = json.loads(caracteristicas.read())
        except:
            return jsonify({"msg": "Características no es un JSON válido"}), 400

    db.session.commit()  # Commit final

    return jsonify({"message": "Producto creado", "id": producto.id}), 201

# Actualizar producto (ADMIN)
@productos_bp.route("/<int:id>", methods=["PATCH"])
def actualizar_producto(id):
    producto = Producto.query.get_or_404(id)
    data = request.get_json() or {}
    if "nombre" in data:
        producto.nombre = data["nombre"]
    if "descripcion" in data:
        producto.descripcion = data["descripcion"]
    if "precio" in data:
        producto.precio = data["precio"]
    if "stock" in data:
        producto.stock = data["stock"]
    if "categoria_id" in data:
        producto.categoria_id = data["categoria_id"]
    
    db.session.commit()
    return jsonify({"message": "Producto actualizado"}), 200

# Eliminar producto (ADMIN)
@productos_bp.route("/<int:id>", methods=["DELETE"])
def eliminar_producto(id):
    producto = Producto.query.get_or_404(id)
    db.session.delete(producto)
    db.session.commit()
    return jsonify({"message": "Producto eliminado"}), 200


from sqlalchemy import text
@productos_bp.route("/reparar_json", methods=["GET"])
def reparar_json():
    # Solo traemos id y especificaciones como string
    productos = db.session.execute(text("SELECT id, especificaciones FROM productos")).fetchall()
    rotos = []

    for p in productos:
        id_ = p.id
        espec = p.especificaciones
        try:
            import json
            if espec:  # si no es None o vacío
                _ = json.loads(espec)
        except (json.JSONDecodeError, TypeError):
            rotos.append(id_)
            # corregimos automáticamente
            db.session.execute(
                text("UPDATE productos SET especificaciones = '{}' WHERE id = :id"),
                {"id": id_}
            )

    db.session.commit()
    return jsonify({
        "productos_corregidos": rotos,
        "total_corregidos": len(rotos)
    })


