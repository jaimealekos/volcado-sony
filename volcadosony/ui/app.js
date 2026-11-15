/*
 * Vista de VolcadoSony: pinta lo que le llega de Python y llama a `Api`.
 * Sin dependencias. Python entrega con window.recibir(eventos).
 * Los datos siempre se escriben con textContent: nunca innerHTML.
 */

"use strict";

const SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏";
const SPIN_MS = 80;
// Bloques de texto de sobra: la barra los recorta al ancho de su columna.
const MB = 1e6;
const GB = 1e9;
const CONFIRMAR_MS = 4000;
const STOP_DEL = "Detener y borrar lo copiado";


const view = {
  api: null,
  jornadas: [],
  jornadaPorIndice: new Map(),
  imagenes: new Map(),
  zoomTimer: null,
  destino: "",
  existe: false,
  valido: false,
  nombreTocado: false,
  pidiendo: false,
  volcando: false,
  ajustarAlto: false,
  terminado: false,
  seccion: "sec-card",
  spinnerTimer: null,
  pausado: false,
  tituloVolcado: "",
  confirmarBorrarTimer: null,
};

const $ = (selector) => document.querySelector(selector);

function crear(etiqueta, clase = null, texto = null) {
  const nodo = document.createElement(etiqueta);
  if (clase) nodo.className = clase;
  if (texto !== null) nodo.textContent = texto;
  return nodo;
}

function escribir(nodo, texto) {
  if (nodo.textContent !== texto) nodo.textContent = texto;
}

function revelar(id) {
  view.seccion = id;
  const seccion = document.getElementById(id);
  if (!seccion) return;
  const reducido = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  seccion.scrollIntoView({ block: "start", behavior: reducido ? "auto" : "smooth" });
}

/* -------------------------- Llamadas a Python -------------------------- */

async function llamar(metodo, ...args) {
  if (!view.api || typeof view.api[metodo] !== "function") return {};
  try {
    return (await view.api[metodo](...args)) ?? {};
  } catch (error) {
    avisar(`No se pudo llamar a ${metodo}: ${error}`);
    return {};
  }
}

/* --------------------------- Alto de ventana ---------------------------- */

// Desde que empieza el volcado, si el contenido no cabe, se pide a Python que
// la ventana crezca lo que falta (dentro del área útil de la pantalla). El
// cálculo del alto final va en Python: aquí outerHeight es el del control web,
// no el de la ventana con su marco.
function ajustarAltoVentana() {
  if (!view.ajustarAlto) return;
  const falta = Math.ceil(document.documentElement.scrollHeight - window.innerHeight);
  if (falta <= 0) return;
  llamar("ajustar_ventana", falta, screen.availHeight, screen.availTop ?? 0);
}

function vigilarAltoVentana() {
  const observador = new ResizeObserver(() => ajustarAltoVentana());
  observador.observe(document.body);
}

/* ------------------------------ Avisos --------------------------------- */

function avisar(texto) {
  const caja = $(`#avisos-${view.seccion.replace("sec-", "")}`) ?? $("#avisos-card");
  caja.append(crear("p", "aviso", `⚠ ${texto}`));
}

/* ------------------------------ Tarjeta -------------------------------- */

function pararSpinner() {
  if (view.spinnerTimer !== null) {
    clearInterval(view.spinnerTimer);
    view.spinnerTimer = null;
  }
}

function mostrarEstado(clase, glifo, texto, girando = false) {
  pararSpinner();
  const linea = $("#card-status");
  linea.hidden = false;
  linea.className = `status status--${clase}`;
  const simbolo = crear("span", "status__glyph", glifo);
  linea.replaceChildren(simbolo, crear("span", "status__text", texto));
  if (girando) {
    let indice = 0;
    simbolo.textContent = SPINNER[indice++ % SPINNER.length];
    view.spinnerTimer = setInterval(() => {
      simbolo.textContent = SPINNER[indice++ % SPINNER.length];
    }, SPIN_MS);
  }
  revelar("sec-card");
}

function ocultarTarjetaExtra() {
  $("#card-list").hidden = true;
  $("#card-list").replaceChildren();
  $("#card-manual").hidden = true;
}

function ocultarDesdeTarjeta() {
  $("#sec-summary").hidden = true;
  $("#sec-dest").hidden = true;
  $("#sec-days").hidden = true;
  $("#sec-space").hidden = true;
}

function mostrarTarjetas(rutas) {
  ocultarDesdeTarjeta();
  mostrarEstado("warn", "!", "Se han detectado varias tarjetas:");
  const lista = $("#card-list");
  lista.replaceChildren();
  rutas.forEach((ruta) => {
    const usar = crear("button", "btn", "Usar");
    usar.type = "button";
    usar.addEventListener("click", () => llamar("usar_tarjeta", ruta));
    const fila = crear("div", "cards__row");
    fila.append(crear("span", "cards__path", ruta), usar);
    lista.append(fila);
  });
  lista.hidden = false;
  $("#card-manual").hidden = true;
}

function mostrarSinTarjeta(mensaje) {
  ocultarDesdeTarjeta();
  mostrarEstado("err", "✖", mensaje);
  $("#card-manual").hidden = false;
}

function pintarResumen(resumen) {
  const tabla = $("#summary");
  tabla.replaceChildren();

  const fila = (rotulo, contenido, clase = null) => {
    const tr = crear("tr", clase);
    tr.append(crear("th", null, rotulo));
    const td = crear("td", clase);
    if (contenido instanceof Node) td.append(contenido);
    else td.textContent = contenido;
    tr.append(td);
    tabla.append(tr);
  };

  fila("Tarjeta", resumen.tarjeta ?? "");
  fila("Brutos", resumen.brutos ?? "");
  fila("Proxies", resumen.proxies ?? "");
  if (resumen.huerfanos) fila("", resumen.huerfanos, "is-warn");

  const jornadas = String(resumen.jornadas ?? "0");
  const corte = jornadas.indexOf("(");
  const cantidad = corte < 0 ? jornadas : jornadas.slice(0, corte).trim();
  const fechas = corte < 0 ? "" : jornadas.slice(corte);
  const contenido = document.createDocumentFragment();
  contenido.append(document.createTextNode(cantidad));
  if (fechas) contenido.append(crear("span", "is-dim", ` ${fechas}`));
  fila("Jornadas", contenido);
}

/* ------------------------------ Jornadas -------------------------------- */

function formatearTamano(bytes) {
  return bytes < GB
    ? `${Math.round(bytes / MB)} MB`
    : `${(bytes / GB).toFixed(1)} GB`;
}

function claveMiniatura(indice, cual) {
  return `${indice}|${cual}`;
}

function crearMiniatura(jornada, cual, nombre) {
  const miniatura = crear("figure", "thumb");
  miniatura.tabIndex = 0;
  miniatura.dataset.indice = String(jornada.indice);
  miniatura.dataset.cual = cual;
  miniatura.title = nombre;
  miniatura.append(crear("span", "thumb__box", "…"));
  miniatura.addEventListener("mouseenter", () => abrirZoom(miniatura));
  miniatura.addEventListener("mouseleave", cerrarZoom);
  miniatura.addEventListener("focus", () => abrirZoom(miniatura));
  miniatura.addEventListener("blur", cerrarZoom);
  return miniatura;
}

function pintarJornadas(jornadas) {
  view.jornadas = jornadas;
  view.jornadaPorIndice = new Map(jornadas.map((j) => [j.indice, j]));
  view.imagenes = new Map();
  const contenedor = $("#days");
  contenedor.replaceChildren();

  for (const jornada of jornadas) {
    const check = document.createElement("input");
    check.type = "checkbox";
    check.checked = true;
    check.dataset.indice = String(jornada.indice);
    const caja = crear("span", "check__box");
    caja.setAttribute("aria-hidden", "true");
    const etiqueta = crear("label", "check");
    etiqueta.append(check, caja);

    const titulo = crear("span", "day__title");
    titulo.append(
      crear("b", "day__lote", jornada.titulo),
      document.createTextNode(" · "),
      crear("b", "day__date", jornada.fecha),
      document.createTextNode(` · ${jornada.detalle}`),
    );

    const nombres = [jornada.nombres.join("  ")];
    if (jornada.mas) nombres.push(`y ${jornada.mas} más...`);
    const cuerpo = crear("span", "day__body");
    cuerpo.append(titulo, crear("span", "day__names", nombres.join("  ")));

    const miniaturas = crear("div", "day__thumbs");
    const cuales = Number(jornada.brutos) > 1
      ? ["primero", "ultimo"]
      : ["primero"];
    for (const cual of cuales) {
      const nombre = (cual === "primero" ? jornada.primero : jornada.ultimo) ?? "";
      miniaturas.append(crearMiniatura(jornada, cual, nombre));
    }

    const fila = crear("div", "day");
    fila.append(etiqueta, cuerpo, miniaturas);
    contenedor.append(fila);
  }

  $("#all-days").checked = true;
  $("#all-days").indeterminate = false;
  pintarSeleccion();
}

function pintarMiniatura(evento) {
  const miniatura = document.querySelector(
    `.thumb[data-indice="${evento.indice}"][data-cual="${evento.cual}"]`);
  if (!miniatura) return;

  const nombre = typeof evento.nombre === "string" ? evento.nombre : "";
  if (nombre) {
    miniatura.title = nombre;
  }
  const clave = claveMiniatura(evento.indice, evento.cual);
  const datos = typeof evento.datos === "string" ? evento.datos : "";
  if (!datos.startsWith("data:image/jpeg;base64,")) {
    view.imagenes.delete(clave);
    miniatura.replaceChildren(crear("span", "thumb__none", "sin imagen"));
    return;
  }

  view.imagenes.set(clave, { datos, nombre: nombre || miniatura.title });
  const imagen = crear("img", "thumb__img");
  imagen.src = datos;
  imagen.alt = "";
  miniatura.replaceChildren(imagen);
}

function posicionarZoom(miniatura) {
  const zoom = $("#zoom");
  const margen = 8;
  const caja = miniatura.getBoundingClientRect();
  zoom.style.insetBlockStart = "0px";
  zoom.style.insetInlineStart = "0px";
  const tamano = zoom.getBoundingClientRect();

  let arriba = caja.bottom + margen;
  if (arriba + tamano.height > window.innerHeight - margen) {
    arriba = caja.top - margen - tamano.height;
  }
  arriba = Math.max(margen,
    Math.min(arriba, window.innerHeight - tamano.height - margen));
  let izquierda = caja.left;
  izquierda = Math.max(margen,
    Math.min(izquierda, window.innerWidth - tamano.width - margen));

  zoom.style.insetBlockStart = `${arriba}px`;
  zoom.style.insetInlineStart = `${izquierda}px`;
}

function abrirZoom(miniatura) {
  const clave = claveMiniatura(miniatura.dataset.indice, miniatura.dataset.cual);
  const imagen = view.imagenes.get(clave);
  if (!imagen) return;

  const zoom = $("#zoom");
  clearTimeout(view.zoomTimer);
  view.zoomTimer = null;
  $("#zoom-img").src = imagen.datos;
  const etiqueta = miniatura.dataset.cual === "primero"
    ? "Primer clip"
    : "Último clip";
  $("#zoom-foot").textContent = `${etiqueta} · ${imagen.nombre}`;
  zoom.hidden = false;
  posicionarZoom(miniatura);
  void zoom.offsetWidth;
  zoom.classList.add("is-open");
}

function cerrarZoom() {
  const zoom = $("#zoom");
  if (zoom.hidden) return;
  zoom.classList.remove("is-open");
  const reducido = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  clearTimeout(view.zoomTimer);
  view.zoomTimer = setTimeout(() => {
    zoom.hidden = true;
    view.zoomTimer = null;
  }, reducido ? 0 : 120);
}

function indicesMarcados() {
  return [...document.querySelectorAll("#days input:checked")]
    .map((check) => Number(check.dataset.indice));
}

function resumenSeleccion() {
  const total = { brutos: 0, proxies: 0, necesario: 0 };
  for (const indice of indicesMarcados()) {
    const jornada = view.jornadaPorIndice.get(indice);
    if (!jornada) continue;
    total.brutos += Number(jornada.brutos) || 0;
    total.proxies += Number(jornada.proxies) || 0;
    total.necesario += Number(jornada.necesario) || 0;
  }
  return total;
}

function puedeVolcar() {
  return !view.volcando
    && !view.terminado
    && view.valido
    && indicesMarcados().length > 0;
}

function pintarSeleccion() {
  const total = resumenSeleccion();
  escribir(
    $("#selection"),
    `Seleccionado: ${total.brutos} brutos + ${total.proxies} proxies · `
      + formatearTamano(total.necesario),
  );
  const marcadas = indicesMarcados().length;
  const todas = view.jornadas.length > 0 && marcadas === view.jornadas.length;
  $("#all-days").checked = todas;
  $("#all-days").indeterminate = marcadas > 0 && !todas;
  $("#btn-dump").disabled = !puedeVolcar();
}

/* ------------------------------- Destino -------------------------------- */

// Mismo formato que la v1: "AAAA.MM.DD - ", con la fecha local.
function nombrePorDefecto(fecha = new Date()) {
  const dos = (numero) => String(numero).padStart(2, "0");
  return `${fecha.getFullYear()}.${dos(fecha.getMonth() + 1)}.${dos(fecha.getDate())} - `;
}

async function revisarDestino() {
  const respuesta = await llamar(
    "revisar_destino", $("#dest-name").value, $("#dest-path").value);
  view.destino = respuesta.destino ?? "";
  view.existe = Boolean(respuesta.existe);
  view.valido = Boolean(respuesta.valido);
  pintarDestino();
  pintarSeleccion();
}

function pintarDestino() {
  const nota = $("#dest-note");
  const invalido = view.nombreTocado && !view.valido;
  $("#dest-name").setAttribute("aria-invalid", invalido ? "true" : "false");
  if (!view.valido) {
    nota.hidden = true;
    escribir(nota, "");
    return;
  }
  nota.hidden = false;
  if (view.existe) {
    nota.className = "note note--warn";
    escribir(nota, `La carpeta ${view.destino} ya existe: se añadirá contenido `
      + "(lo idéntico se omite).");
  } else {
    nota.className = "note";
    escribir(nota, `Destino: ${view.destino}`);
  }
}

/* ------------------------------- Volcado -------------------------------- */

function formatearGB(bytes) {
  return (bytes / GB).toFixed(1);
}

function formatearReloj(segundos) {
  if (segundos === null || segundos === undefined) return "—";
  const total = Math.max(0, Math.floor(segundos));
  const horas = Math.floor(total / 3600);
  const minutos = String(Math.floor((total % 3600) / 60)).padStart(2, "0");
  const resto = String(total % 60).padStart(2, "0");
  return `${horas}:${minutos}:${resto}`;
}

function pintarTituloVolcado() {
  const nodo = crear("span", null, view.tituloVolcado);
  if (view.pausado) nodo.append(crear("span", "rule__paused", " · EN PAUSA"));
  $("#progress-rule").replaceChildren(nodo);
}

function cancelarConfirmarBorrar() {
  clearTimeout(view.confirmarBorrarTimer);
  view.confirmarBorrarTimer = null;
  const boton = $("#btn-stop-del");
  boton.textContent = STOP_DEL;
  boton.dataset.confirmando = "no";
}

function actualizarPausa(pausado) {
  const cambio = view.pausado !== pausado;
  view.pausado = pausado;
  $("#sec-progress").classList.toggle("is-paused", pausado);
  escribir($("#btn-pause"), pausado ? "Reanudar" : "Pausar");
  $("#btn-stop-keep").hidden = !pausado;
  $("#btn-stop-del").hidden = !pausado;
  if (!pausado) cancelarConfirmarBorrar();
  if (cambio) pintarTituloVolcado();
}

function ocultarControles() {
  $("#dump-controls").hidden = true;
  actualizarPausa(false);
}

function confirmarBorrar() {
  const boton = $("#btn-stop-del");
  if (boton.dataset.confirmando === "si") {
    cancelarConfirmarBorrar();
    llamar("detener", "borrar");
    return;
  }
  boton.dataset.confirmando = "si";
  boton.textContent = "Pulsa otra vez para borrar";
  clearTimeout(view.confirmarBorrarTimer);
  view.confirmarBorrarTimer = setTimeout(cancelarConfirmarBorrar, CONFIRMAR_MS);
}

function pintarBarra(prefijo, etiqueta, hecho, total, velocidad, segundos, eta,
  completa, tipo = null) {
  const fraccion = total > 0 ? Math.min(1, hecho / total) : 0;
  Barras.pintar(prefijo, fraccion, tipo);

  const rotulo = $("#pr-" + prefijo + "-label");
  escribir(rotulo, etiqueta);
  rotulo.title = etiqueta;
  escribir($("#pr-" + prefijo + "-pct"), `${Math.round(fraccion * 100)}%`);
  escribir($("#pr-" + prefijo + "-bytes"),
    `${formatearGB(hecho)}/${formatearGB(total)} GB`);
  escribir($("#pr-" + prefijo + "-time"), formatearReloj(segundos));
  $("#pr-" + prefijo + "-speed").hidden = !completa;
  $("#pr-" + prefijo + "-sep").hidden = !completa;
  $("#pr-" + prefijo + "-eta").hidden = !completa;
  if (completa) {
    escribir($("#pr-" + prefijo + "-speed"),
      velocidad > 0 ? `${Math.round(velocidad / MB)} MB/s` : "—");
    escribir($("#pr-" + prefijo + "-eta"),
      eta === null || eta === undefined ? "—" : `ETA ${formatearReloj(eta)}`);
  }
}

function pintarProgreso(progreso) {
  if ($("#sec-progress").hidden) {
    $("#sec-progress").hidden = false;
    revelar("sec-progress");
  }
  pintarBarra("file", progreso.fichero,
    progreso.fichero_hecho, progreso.fichero_total, 0,
    progreso.segundos, null, false, progreso.tipo);
  pintarBarra("lote", progreso.lote,
    progreso.lote_hecho, progreso.lote_total, 0,
    progreso.segundos, null, false);
  pintarBarra("total", `TOTAL ${progreso.visibles_hechos}/${progreso.visibles_total}`,
    progreso.total_hecho, progreso.total_total, progreso.velocidad,
    progreso.segundos, progreso.eta, true);
  if (typeof progreso.pausado === "boolean") actualizarPausa(progreso.pausado);
}

function anadirError(texto) {
  const caja = $("#errors");
  caja.hidden = false;
  caja.append(crear("p", null, `✖ ${texto}`));
}

function bloquear(activo) {
  for (const selector of ["#dest-name", "#dest-path", "#dest-browse",
    "#all-days", "#days input"]) {
    for (const nodo of document.querySelectorAll(selector)) nodo.disabled = activo;
  }
  $("#btn-dump").disabled = activo || !puedeVolcar();
}

// Datos de la tira de película: peso y miniaturas de cada jornada marcada.
function jornadasPelicula(indices) {
  return indices.map((indice) => {
    const jornada = view.jornadaPorIndice.get(indice);
    const imagen = (cual) => view.imagenes.get(claveMiniatura(indice, cual))?.datos ?? null;
    return { peso: Number(jornada.necesario), primero: imagen("primero"), ultimo: imagen("ultimo") };
  });
}

function empezarVolcado(nombre, ruta, indices) {
  view.volcando = true;
  view.ajustarAlto = true;
  $("#sec-space").hidden = true;
  $("#sec-progress").hidden = false;
  const total = resumenSeleccion();
  view.tituloVolcado = `Volcando ${total.brutos} brutos + ${total.proxies} proxies`
    + ` · ${formatearTamano(total.necesario)}`;
  view.pausado = false;
  $("#dump-controls").hidden = false;
  actualizarPausa(false);
  pintarTituloVolcado();
  Barras.montar(jornadasPelicula(indices));
  for (const prefijo of ["file", "lote", "total"]) {
    pintarBarra(prefijo, "—", 0, 0, 0, 0, null, prefijo === "total");
  }
  $("#errors").hidden = true;
  $("#errors").replaceChildren();
  bloquear(true);
  pintarSeleccion();
  revelar("sec-progress");
  ajustarAltoVentana();
  llamar("volcar", nombre, ruta, indices);
}

async function pedirVolcado() {
  if (view.pidiendo || !puedeVolcar()) return;
  view.pidiendo = true;
  $("#btn-dump").disabled = true;
  try {
    const nombre = $("#dest-name").value;
    const ruta = $("#dest-path").value;
    const indices = indicesMarcados();
    const respuesta = await llamar("preparar", nombre, ruta, indices);
    if (respuesta.ok !== true) {
      const mensaje = typeof respuesta.mensaje === "string" && respuesta.mensaje
        ? respuesta.mensaje
        : "No se pudo comprobar el espacio libre: revisa el destino e "
          + "inténtalo de nuevo.";
      $("#space-text").textContent = `✖ ${mensaje}`;
      $("#sec-space").hidden = false;
      revelar("sec-space");
      return;
    }
    empezarVolcado(nombre, ruta, indices);
  } finally {
    view.pidiendo = false;
    pintarSeleccion();
  }
}

/* ------------------------------ Resultado ------------------------------- */

function pintarResultado(evento) {
  const caja = $("#result");
  caja.className = `result ${evento.ok ? "result--ok" : "result--err"}`;
  caja.replaceChildren();

  caja.append(crear("p", "result__title",
    evento.ok ? "✔ VOLCADO COMPLETADO" : "VOLCADO TERMINADO CON ERRORES"));

  if (evento.errores.length) {
    const lista = crear("div", "result__errors");
    for (const error of evento.errores) lista.append(crear("p", null, `✖ ${error}`));
    caja.append(lista);
  }

  const tabla = crear("table", "result__table");
  for (const [rotulo, valor] of evento.filas) {
    const tr = crear("tr");
    tr.append(crear("th", null, rotulo), crear("td", null, valor));
    tabla.append(tr);
  }
  caja.append(tabla);

  const falloRegistro = String(evento.registro).startsWith("No se pudo");
  caja.append(crear("p", falloRegistro ? "result__log result__log--err" : "result__log",
    evento.registro));

  caja.append(accionesFinales());

  $("#sec-result").hidden = false;
  revelar("sec-result");
}

// Botones del final, tanto si el volcado terminó como si se detuvo.
function accionesFinales() {
  const acciones = crear("div", "result__actions");
  const salir = crear("button", "btn btn--primary", "Salir");
  salir.type = "button";
  salir.addEventListener("click", () => llamar("salir"));
  const reiniciar = crear("button", "btn", "Reiniciar");
  reiniciar.type = "button";
  reiniciar.addEventListener("click", reiniciarSesion);
  acciones.append(salir, reiniciar);
  return acciones;
}

// Vuelve al principio: Python deja la sesión limpia y la página se recarga,
// con lo que busca la tarjeta otra vez como al abrir.
async function reiniciarSesion() {
  if (await llamar("reiniciar") === true) location.reload();
}

function terminar(evento) {
  view.volcando = false;
  view.terminado = true;
  ocultarControles();
  pintarResultado(evento);
}

function terminarDetenido(evento) {
  view.volcando = false;
  view.terminado = true;
  ocultarControles();
  for (const error of evento.errores ?? []) anadirError(error);

  const linea = evento.modo === "conservar"
    ? `Volcado detenido. Se conservan ${evento.copiados} ficheros copiados. `
      + `${evento.registro}`
    : "Volcado detenido. Se borraron "
      + `${evento.borrados} ficheros copiados en esta sesión.`;

  const caja = $("#result");
  caja.className = "result result--detenido";
  caja.replaceChildren(crear("p", "result__log", linea));

  caja.append(accionesFinales());

  $("#sec-result").hidden = false;
  revelar("sec-result");
}

/* ---------------------------- Eventos de Python ------------------------- */

function recibir(eventos) {
  for (const evento of eventos) aplicar(evento);
}
window.recibir = recibir;

function aplicar(evento) {
  switch (evento.type) {
    case "buscando":
      ocultarTarjetaExtra();
      ocultarDesdeTarjeta();
      mostrarEstado("spin", "", "Buscando tarjeta SD de Sony...", true);
      break;

    case "tarjetas":
      mostrarTarjetas(evento.rutas);
      break;

    case "sin_tarjeta":
      mostrarSinTarjeta(evento.mensaje);
      break;

    case "escaneando":
      ocultarTarjetaExtra();
      ocultarDesdeTarjeta();
      mostrarEstado("spin", "", "Escaneando la tarjeta...", true);
      break;

    case "tarjeta": {
      ocultarTarjetaExtra();
      if (evento.vacia) {
        ocultarDesdeTarjeta();
        mostrarEstado("warn", "!",
          "La tarjeta no contiene ningún bruto en PRIVATE\\M4ROOT\\CLIP");
        break;
      }
      mostrarEstado("ok", "✔", `Tarjeta SD detectada en ${evento.ruta}`);
      pintarResumen(evento.resumen);
      pintarJornadas(evento.jornadas);
      $("#sec-summary").hidden = false;
      $("#sec-dest").hidden = false;
      $("#sec-days").hidden = false;
      const nombre = $("#dest-name");
      nombre.value = nombrePorDefecto();
      nombre.setSelectionRange(nombre.value.length, nombre.value.length);
      $("#dest-path").value = "";
      $("#dest-path").placeholder = evento.escritorio || "Escritorio";
      view.nombreTocado = false;
      revisarDestino();
      revelar("sec-summary");
      break;
    }

    case "miniatura":
      pintarMiniatura(evento);
      break;

    case "aviso":
      avisar(evento.texto);
      break;

    case "progreso":
      pintarProgreso(evento);
      break;

    case "error":
      anadirError(evento.texto);
      break;

    case "fin":
      terminar(evento);
      break;

    case "detenido":
      terminarDetenido(evento);
      break;

    case "cancelado":
      view.volcando = false;
      ocultarControles();
      avisar("Volcado cancelado.");
      break;
  }
}

/* ------------------------------- Controles ------------------------------ */

function conectarControles() {
  $("#card-use").addEventListener("click", () => {
    const texto = $("#card-input").value;
    if (texto.trim()) llamar("usar_tarjeta", texto);
  });
  $("#card-input").addEventListener("keydown", (evento) => {
    if (evento.key === "Enter") $("#card-use").click();
  });
  $("#card-search").addEventListener("click", () => llamar("buscar_de_nuevo"));

  $("#dest-name").addEventListener("input", () => {
    view.nombreTocado = true;
    revisarDestino();
  });
  $("#dest-name").addEventListener("blur", () => {
    view.nombreTocado = true;
    revisarDestino();
  });
  $("#dest-path").addEventListener("input", revisarDestino);
  for (const selector of ["#dest-name", "#dest-path"]) {
    $(selector).addEventListener("keydown", (evento) => {
      if (evento.key === "Enter" && !$("#btn-dump").disabled) {
        evento.preventDefault();
        $("#btn-dump").click();
      }
    });
  }
  $("#dest-browse").addEventListener("click", async () => {
    const ruta = await llamar("examinar", $("#dest-path").value);
    if (typeof ruta === "string" && ruta) {
      $("#dest-path").value = ruta;
      revisarDestino();
    }
  });

  $("#all-days").addEventListener("change", (evento) => {
    for (const check of document.querySelectorAll("#days input")) {
      check.checked = evento.target.checked;
    }
    pintarSeleccion();
  });
  $("#days").addEventListener("change", pintarSeleccion);

  $("#btn-dump").addEventListener("click", pedirVolcado);
  $("#btn-pause").addEventListener("click", () => {
    llamar(view.pausado ? "reanudar" : "pausar");
  });
  $("#btn-stop-keep").addEventListener("click", () => llamar("detener", "conservar"));
  $("#btn-stop-del").addEventListener("click", confirmarBorrar);
  $("#space-continue").addEventListener("click", () => {
    empezarVolcado($("#dest-name").value, $("#dest-path").value, indicesMarcados());
  });
  $("#space-cancel").addEventListener("click", () => {
    $("#sec-space").hidden = true;
  });
}

function conectarApi() {
  if (view.api || !window.pywebview || !window.pywebview.api) return;
  view.api = window.pywebview.api;
  llamar("iniciar");
}

document.addEventListener("DOMContentLoaded", () => {
  conectarControles();
  vigilarAltoVentana();
  conectarApi();
});
window.addEventListener("pywebviewready", conectarApi);
