const BASE_URL = "http://localhost:5000/api/productos"; // Asegúrate de que esta URL sea correcta

// Función para mostrar la respuesta en el HTML
const mostrarRespuesta = (elementId, data, status) => {
    const responseDiv = document.getElementById(elementId);
    responseDiv.innerHTML = `<h3>Estado: ${status}</h3><pre>${JSON.stringify(data, null, 2)}</pre>`;
};

// Listar productos
const listarProductos = async () => {
    try {
        const response = await fetch(BASE_URL);
        const data = await response.json();
        mostrarRespuesta("listar-response", data, response.status);
    } catch (error) {
        mostrarRespuesta("listar-response", { error: error.message }, 500);
    }
};

// Detalle de un producto
document.getElementById("detalle-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const id = document.getElementById("detalle-id").value;
    try {
        const response = await fetch(`${BASE_URL}/${id}`);
        const data = await response.json();
        mostrarRespuesta("detalle-response", data, response.status);
    } catch (error) {
        mostrarRespuesta("detalle-response", { error: error.message }, 500);
    }
});

// Crear producto
document.getElementById("crear-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.target;
    const formData = new FormData();

    // Agregar campos de texto al FormData
    formData.append("nombre", form.nombre.value);
    formData.append("marca", form.marca.value);
    formData.append("descripcion", form.descripcion.value);
    formData.append("precio", form.precio.value);
    formData.append("stock", form.stock.value);
    formData.append("peso", form.peso.value);
    formData.append("categoria_id", form.categoria_id.value);
    
    // Agregar imagen principal (una sola)
    const imagenPrincipal = form.url_imagen_principal.files[0];
    if (imagenPrincipal) {
        // En tu backend, este input se espera con el nombre "url_imagen_principal"
        // Si tu backend lo espera con otro nombre, cámbialo aquí.
        // formData.append("url_imagen_principal", imagenPrincipal);
        // Sin embargo, tu backend parece esperar todo como "url_imagenes",
        // así que agreguemos la principal con ese mismo nombre para probar.
        formData.append("url_imagenes", imagenPrincipal);
    }

    // Agregar imágenes secundarias (múltiples)
    const imagenesSecundarias = form.url_imagenes.files;
    for (let i = 0; i < imagenesSecundarias.length; i++) {
        // El backend espera el campo "url_imagenes" para las demás imágenes.
        formData.append("url_imagenes", imagenesSecundarias[i]);
    }
    
    try {
        const response = await fetch(BASE_URL, {
            method: "POST",
            body: formData,
        });
        const data = await response.json();
        mostrarRespuesta("crear-response", data, response.status);
    } catch (error) {
        mostrarRespuesta("crear-response", { error: error.message }, 500);
    }
});

// Actualizar producto
document.getElementById("actualizar-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.target;
    const id = form["actualizar-id"].value;
    
    const data = {};
    if (form["actualizar-nombre"].value) data.nombre = form["actualizar-nombre"].value;
    if (form["actualizar-descripcion"].value) data.descripcion = form["actualizar-descripcion"].value;
    if (form["actualizar-precio"].value) data.precio = form["actualizar-precio"].value;
    if (form["actualizar-stock"].value) data.stock = form["actualizar-stock"].value;
    if (form["actualizar-categoria_id"].value) data.categoria_id = form["actualizar-categoria_id"].value;

    try {
        const response = await fetch(`${BASE_URL}/${id}`, {
            method: "PATCH",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify(data),
        });
        const responseData = await response.json();
        mostrarRespuesta("actualizar-response", responseData, response.status);
    } catch (error) {
        mostrarRespuesta("actualizar-response", { error: error.message }, 500);
    }
});

// Eliminar producto
document.getElementById("eliminar-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const id = document.getElementById("eliminar-id").value;
    try {
        const response = await fetch(`${BASE_URL}/${id}`, {
            method: "DELETE",
        });
        const data = await response.json();
        mostrarRespuesta("eliminar-response", data, response.status);
    } catch (error) {
        mostrarRespuesta("eliminar-response", { error: error.message }, 500);
    }
});