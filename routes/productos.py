import os
from flask import Blueprint, json, request, jsonify
from models import ImagenProducto, Producto, Usuario
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

def is_admin():
    """
    Asume que get_jwt_identity() devuelve un dict con rol,
    o un id de usuario. Si devuelve id, buscamos el usuario.
    """
    identity = get_jwt_identity()

    # Caso 1: identity ya viene como dict {id, rol, ...}
    if isinstance(identity, dict):
        return identity.get("rol") == "admin"

    # Caso 2: identity es el id del usuario
    try:
        user = Usuario.query.get(int(identity))
        return user and user.rol == "admin"
    except:
        return False

#------------------
#-----ENDPOINTS----
#------------------

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

        productos = (
            Producto.query
            .filter(Producto.categoria_id.in_(categoria_ids))
            .filter(Producto.activo == True)   # ✅
            .order_by(desc(Producto.vistas * 0.7 + Producto.valoracion_promedio * 0.3))
            .limit(per_page)
            .offset(offset_value)
            .all()
        )

        total = Producto.query.filter(
            Producto.categoria_id.in_(categoria_ids),
            Producto.activo == True           # ✅
        ).count()

        return jsonify({
            "page": page,
            "per_page": per_page,
            "total": total,
            "productos": [
                {
                    "id": p.id,
                    "nombre": p.nombre,
                    "precio": p.precio,
                    "activo": p.activo,
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

# Detalle de un producto
@productos_bp.route("/<int:id>", methods=["GET"])
def detalle_producto(id):
    try:
        p = Producto.query.get(id)
        
        if not p:
            return jsonify({"msg": "Producto no encontrado"}), 404

        # Si está inactivo: que el público no lo vea
        if not p.activo:
            return jsonify({"msg": "Producto no encontrado"}), 404
        
        p.vistas += 1
        db.session.commit()
        # --- Obtener sugerencias ---
        sugeridos = (
            Producto.query
            .filter(
                Producto.categoria_id == p.categoria_id,
                Producto.id != p.id,
                Producto.activo == True  # ✅
            )
            .order_by(Producto.vistas.desc(), Producto.valoracion_promedio.desc())
            .limit(8)
            .all()
        )

        sugeridos_data = [
            {
                "id": s.id,
                "nombre": s.nombre,
                "precio": s.precio,
                "url_imagen_principal": s.url_imagen_principal,
                "url_imagen_secundaria": s.imagenes[0].url_imagen if s.imagenes else None
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
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 10))
        offset_value = (page - 1) * per_page

        include_inactive = request.args.get("include_inactive", "false").lower() == "true"

        query = Producto.query

        # Público: solo activos
        if not include_inactive:
            query = query.filter(Producto.activo == True)
        else:
            # Si piden include_inactive, solo permitir si es admin autenticado
            # (si no querés esto, lo sacamos)
            from flask_jwt_extended import verify_jwt_in_request
            try:
                verify_jwt_in_request(optional=True)
                if not is_admin():
                    return jsonify({"msg": "No autorizado"}), 403
            except:
                return jsonify({"msg": "No autorizado"}), 403

        productos = (
            query
            .order_by(desc(Producto.vistas * 0.7 + Producto.valoracion_promedio * 0.3))
            .limit(per_page)
            .offset(offset_value)
            .all()
        )

        total = query.count()

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
                    "activo": p.activo,  # ✅ útil para admin/front
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
    activo=True,
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
@jwt_required()
def actualizar_producto(id):
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

# Eliminar producto (ADMIN)
@productos_bp.route("/<int:id>", methods=["DELETE"])
@jwt_required()
def eliminar_producto(id):
    producto = Producto.query.get_or_404(id)
    producto.activo=False
    db.session.commit()
    return jsonify({"message": "Producto desactivado"}), 200

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

