/*
 * Vista de VolcadoSony: pinta lo que le llega de Python y llama a `Api`.
 * Sin dependencias. Python entrega con window.recibir(eventos).
 * Los datos siempre se escriben con textContent: nunca innerHTML.
 */

"use strict";

const SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏";
const SPIN_MS = 80;
// Bloques de texto de sobra: la barra los recorta al ancho de su columna.
const BLOCKS = 200;
const MB = 1e6;
const GB = 1e9;

const ICONO = { bruto: "🎬", proxy: "🎞", xml: "📄" };

const view = {
  api: null,
  jornadas: [],
  jornadaPorIndice: new Map(),
  destino: "",
  existe: false,
  valido: false,
  nombreTocado: false,
  pidiendo: false,
  volcando: false,
  terminado: false,
  seccion: "sec-card",
  spinnerTimer: null,
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

function pintarJornadas(jornadas) {
  view.jornadas = jornadas;
  view.jornadaPorIndice = new Map(jornadas.map((j) => [j.indice, j]));
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

    const fila = crear("div", "day");
    fila.append(etiqueta, cuerpo);
    contenedor.append(fila);
  }

  $("#all-days").checked = true;
  $("#all-days").indeterminate = false;
  pintarSeleccion();
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

function pintarBarra(prefijo, etiqueta, hecho, total, velocidad, segundos, eta,
  completa) {
  const fraccion = total > 0 ? Math.min(1, hecho / total) : 0;
  const hecha = $("#pr-" + prefijo + "-done");
  if (!hecha.textContent) {
    hecha.textContent = "█".repeat(BLOCKS);
    $("#pr-" + prefijo + "-rest").textContent = "░".repeat(BLOCKS);
  }
  hecha.style.width = `${fraccion * 100}%`;
  $("#pr-" + prefijo + "-done").parentElement.classList.toggle(
    "bar--full", fraccion >= 1);

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
  const icono = ICONO[progreso.tipo] ?? "📄";
  pintarBarra("file", `${icono} ${progreso.fichero}`,
    progreso.fichero_hecho, progreso.fichero_total, 0,
    progreso.segundos, null, false);
  pintarBarra("lote", progreso.lote,
    progreso.lote_hecho, progreso.lote_total, 0,
    progreso.segundos, null, false);
  pintarBarra("total", `TOTAL ${progreso.visibles_hechos}/${progreso.visibles_total}`,
    progreso.total_hecho, progreso.total_total, progreso.velocidad,
    progreso.segundos, progreso.eta, true);
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

function empezarVolcado(nombre, ruta, indices) {
  view.volcando = true;
  $("#sec-space").hidden = true;
  $("#sec-progress").hidden = false;
  const total = resumenSeleccion();
  const titulo = crear("span", null,
    `Volcando ${total.brutos} brutos + ${total.proxies} proxies`
      + ` · ${formatearTamano(total.necesario)}`);
  $("#progress-rule").replaceChildren(titulo);
  for (const prefijo of ["file", "lote", "total"]) {
    pintarBarra(prefijo, "—", 0, 0, 0, 0, null, prefijo === "total");
  }
  $("#errors").hidden = true;
  $("#errors").replaceChildren();
  bloquear(true);
  pintarSeleccion();
  revelar("sec-progress");
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

  const acciones = crear("div", "result__actions");
  const salir = crear("button", "btn btn--primary", "Salir");
  salir.type = "button";
  salir.addEventListener("click", () => llamar("salir"));
  acciones.append(salir);
  caja.append(acciones);

  $("#sec-result").hidden = false;
  revelar("sec-result");
}

function terminar(evento) {
  view.volcando = false;
  view.terminado = true;
  pintarResultado(evento);
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
      $("#dest-name").value = "";
      $("#dest-path").value = "";
      $("#dest-path").placeholder = evento.escritorio || "Escritorio";
      view.nombreTocado = false;
      revisarDestino();
      revelar("sec-summary");
      break;
    }

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

    case "cancelado":
      view.volcando = false;
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
  conectarApi();
});
window.addEventListener("pywebviewready", conectarApi);
