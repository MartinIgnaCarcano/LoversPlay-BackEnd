import os
from flask import Blueprint, json, request, jsonify
from models import ImagenProducto, Producto, Usuario, Categoria, Pedido, PedidoDetalle
from werkzeug.utils import secure_filename
from database import db
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import desc, asc, func, or_

productos_bp = Blueprint("productos", __name__, url_prefix="/api/productos")

UPLOAD_FOLDER = "static/uploads"
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
        "┬": "",
        "├▒": "ñ"
    }
    for roto, bien in reemplazos.items():
        texto = texto.replace(roto, bien)
    return texto

def require_admin():
    user_id = get_jwt_identity()
    user = Usuario.query.get(int(user_id))
    if not user or user.rol != "admin":
        return None
    return user

#------------------
#------USER--------
#------------------

#REVISAR-----v

@productos_bp.route("/", methods=["GET"])
def listar_productos():
    try:
        preUrl = os.getenv("URL_BASE_IMG")
        # ------------------------
        # Params
        # ------------------------
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 12))

        min_price = request.args.get("min_price", 0)
        max_price = request.args.get("max_price", 100000)
        en_stock = request.args.get("en_stock", "0")
        sort = request.args.get("sort", "views")

        categorias_param = request.args.get("categorias")  # ej: "1,2,3"

        # ------------------------
        # Query base
        # ------------------------
        query = Producto.query.filter(Producto.activo.is_(True))

        # ------------------------
        # Filtro categorías (N:N)
        # ------------------------
        if categorias_param:
            categoria_ids = [int(c) for c in categorias_param.split(",") if c.isdigit()]
            if categoria_ids:
                query = (
                    query
                    .join(Producto.categorias)
                    .filter(Categoria.id.in_(categoria_ids))
                    .distinct()
                )

        # ------------------------
        # Filtro stock
        # ------------------------
        if en_stock == "1":
            query = query.filter(Producto.stock > 0)

        # ------------------------
        # Filtro precio
        # ------------------------
        try:
            min_price = max(0, float(min_price))
            max_price = min(100000, float(max_price))
        except ValueError:
            min_price = 0
            max_price = 100000

        query = query.filter(Producto.precio.between(min_price, max_price))

        # ------------------------
        # Orden
        # ------------------------
        if sort == "price_asc":
            query = query.order_by(Producto.precio.asc())
        elif sort == "price_desc":
            query = query.order_by(Producto.precio.desc())
        elif sort == "rating":
            query = query.order_by(desc(Producto.valoracion_promedio))
        else:
            query = query.order_by(desc(Producto.vistas))

        # ------------------------
        # Paginado
        # ------------------------
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        data = [
            {
                "id": p.id,
                "nombre": p.nombre,
                "extra": p.extra,
                "precio": float(p.precio),
                "stock": p.stock,
                "slug": p.slug,
                "url_imagen_principal": preUrl + p.url_imagen_principal,
                "url_imagen_secundaria": preUrl + p.imagenes[0].url_imagen if p.imagenes else None,
                "categorias": [
                    {"id": c.id, "nombre": c.nombre, "slug": c.slug}
                    for c in p.categorias
                ]
            }
            for p in pagination.items
        ]

        return jsonify({
            "items": data,
            "page": page,
            "total": pagination.total,
            "pages": pagination.pages
        })

    except Exception as e:
        return jsonify({"msg": "Error interno", "error": str(e)}), 500

@productos_bp.route("/nombres", methods=["GET"])
def listar_nombres_productos():
    try:
        productos = (
            Producto.query
            .filter(Producto.activo == True)
            .with_entities(Producto.id, Producto.nombre, Producto.categoria_id, Producto.url_imagen_principal)
            .all()
        )
        return jsonify([
            {
                "id": p.id,
                "nombre": fix_encoding(p.nombre),
                "categoria_id": p.categoria_id,
                "url_imagen_principal": p.url_imagen_principal
            } for p in productos
        ])
    except Exception as e:
        return jsonify({"msg": "Error al listar nombres de productos", "error": str(e)}), 500

@productos_bp.route("/<int:id>", methods=["GET"])
def detalle_producto(id):
    try:
        urlImg = os.getenv("URL_BASE_IMG")
        
        p = Producto.query.get(id)

        if not p or not p.activo:
            return jsonify({"msg": "Producto no encontrado"}), 404

        # sumar vista
        p.vistas = (p.vistas or 0) + 1
        db.session.commit()

        cat_ids = [c.id for c in (p.categorias or [])]

        sugeridos = []
        if cat_ids:
            sugeridos = (
                Producto.query
                .join(Producto.categorias)  # requiere relationship bien definido
                .filter(
                    Categoria.id.in_(cat_ids),
                    Producto.id != p.id,
                    Producto.activo.is_(True)
                )
                .distinct()
                .order_by(Producto.vistas.desc(), Producto.valoracion_promedio.desc())
                .limit(8)
                .all()
            )

        sugeridos_data = [
            {
                "id": s.id,
                "precio": s.precio,
                "nombre": s.nombre,
                "extra": s.extra,
                "url_imagen_principal": urlImg + s.url_imagen_principal,
                "url_imagen_secundaria": urlImg + s.imagenes[0].url_imagen if s.imagenes else None,
                "categorias": [
                    {"id": c.id, "nombre": c.nombre, "slug": getattr(c, "slug", None)}
                    for c in (s.categorias or [])
                ],
            }
            for s in sugeridos
        ]

        return jsonify({
            "id": p.id,
            "nombre": p.nombre,
            "extra": p.extra,
            "precio": p.precio,
            "peso": p.peso,
            "stock": p.stock,
            "url_imagen_principal": urlImg + p.url_imagen_principal,

            "categorias": [
                {"id": c.id, "nombre": c.nombre, "slug": getattr(c, "slug", None)}
                for c in (p.categorias or [])
            ],
            
            "slug": p.slug,
            "descripcion_corta": p.descripcion_corta,
            "descripcion_larga": p.descripcion_larga,
            "imagenes": [urlImg + img.url_imagen for img in (p.imagenes or [])],
            "sugeridos": sugeridos_data
        })
    except Exception as e:
        return jsonify({"msg": "Error interno", "error": str(e)}), 500


@productos_bp.route("/filtro", methods=["GET"])
def buscar_por_nombre():
    try:
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 10))
        filtro = request.args.get("filtro", "")
        categoria_id = request.args.get("id", None)

        offset_value = (page - 1) * per_page

        # Base query
        query = Producto.query.filter(Producto.activo == True)

        # -----------------------------
        # APLICAR FILTRO POR NOMBRE
        # -----------------------------
        if filtro:
            query = query.filter(
                Producto.nombre.ilike(f"%{filtro}%")
            )

        # -----------------------------
        # APLICAR FILTRO POR CATEGORIA
        # -----------------------------
        if categoria_id:
            query = query.filter(
                Producto.categoria_id == categoria_id
            )

        # TOTAL PARA PAGINACIÓN
        total = query.count()

        # ORDEN + PAGINADO
        productos = (
            query
            .order_by(desc(Producto.vistas * 0.7 + Producto.valoracion_promedio * 0.3))
            .limit(per_page)
            .offset(offset_value)
            .all()
        )

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
                    "url_imagen_secundaria": p.imagenes[0].url_imagen if p.imagenes else None,
                    "stock": p.stock,
                    "vistas": p.vistas,
                    "valoracion_promedio": p.valoracion_promedio,
                }
                for p in productos
            ]
        })

    except Exception as e:
        return jsonify({"msg": "Error al listar productos", "error": str(e)}), 500

#------------------
#------ADMIN-------
#------------------
# Crear producto 
@productos_bp.route("/", methods=["POST"])
@jwt_required()
def crear_producto():
    admin = require_admin()
    if not admin:
        return jsonify({"error": "Acceso denegado"}), 403
    try:
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
    except Exception as e:
        db.session.rollback()
        print("ERROR:", repr(e))
        return jsonify({"error": "Error interno"}), 500

# Actualizar producto (ADMIN)
@productos_bp.route("/<int:id>", methods=["PATCH"])
@jwt_required()
def actualizar_producto(id):
    admin = require_admin()
    if not admin:
        return jsonify({"error": "Acceso denegado"}), 403
    try:
        producto = Producto.query.get_or_404(id)

        form = request.form

        if "nombre" in form:
            producto.nombre = form.get("nombre")

        if "slug" in form:
            producto.slug = form.get("slug")

        if "descripcion_corta" in form:
            producto.descripcion_corta = form.get("descripcion_corta")

        if "descripcion_larga" in form:
            producto.descripcion_larga = form.get("descripcion_larga")

        if "precio" in form:
            producto.precio = float(form.get("precio"))

        if "stock" in form:
            producto.stock = int(form.get("stock"))

        if "peso" in form:
            producto.peso = float(form.get("peso"))

        if "categoria_id" in form:
            producto.categoria_id = int(form.get("categoria_id"))

        # 🖼️ Imagen principal nueva
        if "imagen_principal" in request.files:
            file = request.files["imagen_principal"]
            if file and allowed_file(file.filename):
                filename = secure_filename(
                    nombreArchivoFinal(file.filename, producto.nombre, producto.id, "principal")
                )
                filepath = os.path.join(UPLOAD_FOLDER, filename)
                file.save(filepath)
                producto.url_imagen_principal = f"/{filepath}"
            else:
                return jsonify({"msg": "Imagen principal no permitida"}), 400

        # 🖼️ Imágenes secundarias nuevas
        if "imagenes" in request.files:
            files = request.files.getlist("imagenes")
            for i, file in enumerate(files):
                if file and allowed_file(file.filename):
                    filename = secure_filename(
                        nombreArchivoFinal(file.filename, producto.nombre, producto.id, i)
                    )
                    filepath = os.path.join(UPLOAD_FOLDER, filename)
                    file.save(filepath)
                    producto.imagenes.append(
                        ImagenProducto(url_imagen=f"/{filepath}")
                    )
                else:
                    return jsonify({"msg": "Imagen secundaria no permitida"}), 400

        db.session.commit()
        return jsonify({"message": "Producto actualizado"}), 200
    except Exception as e:
        db.session.rollback()
        print("ERROR:", repr(e))
        return jsonify({"error": "Error interno"}), 500
    
# Eliminar producto (ADMIN)
@productos_bp.route("/<int:id>", methods=["DELETE"])
@jwt_required()
def eliminar_producto(id):
    admin = require_admin()
    if not admin:
        return jsonify({"error": "Acceso denegado"}), 403
    try:    
        producto = Producto.query.get_or_404(id)
        producto.activo=False
        db.session.commit()
        return jsonify({"message": "Producto desactivado"}), 200
    except Exception as e:
        db.session.rollback()
        print("ERROR:", repr(e))
        return jsonify({"error": "Error interno"}), 500

from sqlalchemy import text
from flask import jsonify

@productos_bp.route("/reparar_textos", methods=["POST"])
def reparar_textos():
    # Traemos columnas reales
    rows = db.session.execute(text("""
        SELECT id, nombre, descripcion_corta, descripcion_larga, extra
        FROM productos
    """)).mappings().all()

    corregidos = 0
    ids_corregidos = []

    for r in rows:
        pid = r["id"]

        nombre = fix_encoding(r["nombre"])
        corta = fix_encoding(r["descripcion_corta"])
        larga = fix_encoding(r["descripcion_larga"])
        extra = fix_encoding(r["extra"])

        # Solo update si cambió algo (evita writes innecesarios)
        if (nombre != r["nombre"] or corta != r["descripcion_corta"] or
            larga != r["descripcion_larga"] or extra != r["extra"]):

            db.session.execute(text("""
                UPDATE productos
                SET nombre = :nombre,
                    descripcion_corta = :corta,
                    descripcion_larga = :larga,
                    extra = :extra
                WHERE id = :id
            """), {
                "id": pid,
                "nombre": nombre,
                "corta": corta,
                "larga": larga,
                "extra": extra
            })

            corregidos += 1
            ids_corregidos.append(pid)

    db.session.commit()

    return jsonify({
        "productos_corregidos": ids_corregidos,
        "total_corregidos": corregidos
    }), 200


# @productos_bp.route("/por_categoria", methods=["GET"])
# def listar_productos():
#     try:
#         # Leer categorías de la query (?ids=1,2,3)
#         ids_param = request.args.get("ids")
#         if not ids_param:
#             return jsonify({"msg": "Debe indicar al menos una categoría"}), 400

#         categoria_ids = [int(cid) for cid in ids_param.split(",") if cid.isdigit()]

#         if not categoria_ids:
#             return jsonify({"msg": "IDs de categoría inválidos"}), 400

#         # Paginación
#         page = int(request.args.get("page", 1))
#         per_page = int(request.args.get("per_page", 10))
#         offset_value = (page - 1) * per_page

#         productos = (
#             Producto.query
#             .filter(Producto.categoria_id.in_(categoria_ids))
#             .filter(Producto.activo == True)   # ✅
#             .order_by(desc(Producto.vistas * 0.7 + Producto.valoracion_promedio * 0.3))
#             .limit(per_page)
#             .offset(offset_value)
#             .all()
#         )

#         total = Producto.query.filter(
#             Producto.categoria_id.in_(categoria_ids),
#             Producto.activo == True           # ✅
#         ).count()

#         return jsonify({
#             "page": page,
#             "per_page": per_page,
#             "total": total,
#             "productos": [
#                 {
#                     "id": p.id,
#                     "nombre": p.nombre,
#                     "precio": p.precio,
#                     "activo": p.activo,
#                     "url_imagen_principal": p.url_imagen_principal,
#                     "url_imagen_secundaria": p.imagenes[0].url_imagen if p.imagenes else None,
#                     "stock": p.stock,
#                     "vistas": p.vistas,
#                     "valoracion_promedio": p.valoracion_promedio,
#                 }
#                 for p in productos
#             ]
#         })
#     except Exception as e:
#         return jsonify({"msg": "Error al listar productos", "error": str(e)}), 500
