/* Barras de progreso de VolcadoSony.
 *
 * - Fichero y lote: barras de bloques de consola con resolución de octavos
 *   de carácter (▏▎▍▌▋▊▉█) y un cabezal que parpadea en el borde de avance.
 *   El color del fichero dice qué se copia: bruto, proxy o XML.
 * - Total: una tira de película hecha con las miniaturas de las jornadas
 *   marcadas. Cada jornada ocupa lo que pesa; lo pendiente se ve en negativo
 *   y lo copiado se «revela» en positivo al pasar la ventanilla de luz.
 */
"use strict";

const Barras = (() => {
  // Octavos de bloque, de 0/8 a 7/8; el bloque entero va aparte.
  const OCTAVOS = ["", "▏", "▎", "▍", "▌", "▋", "▊", "▉"];
  const LLENO = "█";
  const VACIO = "·";
  const MARCA_CADA = 10;        // una marca «╵» cada 10 caracteres de pista
  const FOTOGRAMAS_MAX = 48;    // fotogramas por jornada en la tira
  const IMAGEN_VALIDA = /^data:image\/jpeg;base64,[A-Za-z0-9+/]+=*$/;

  const tipos = ["bruto", "proxy", "xml"];

  function crear(etiqueta, clase) {
    const nodo = document.createElement(etiqueta);
    if (clase) nodo.className = clase;
    return nodo;
  }

  /* --------------------------- Barras de bloques -------------------------- */

  // Anchura de la pista en caracteres, medida con un carácter de muestra.
  function columnas(pista) {
    const muestra = pista.querySelector(".blocks__probe");
    const ancho = muestra.getBoundingClientRect().width;
    return ancho > 0 ? Math.max(1, Math.floor(pista.clientWidth / ancho)) : 0;
  }

  function textoPista(n, fraccion) {
    const exacto = fraccion * n * 8;
    const llenos = Math.floor(exacto / 8);
    const resto = Math.floor(exacto % 8);
    const hecho = LLENO.repeat(llenos) + (llenos < n ? OCTAVOS[resto] : "");
    let pendiente = "";
    for (let i = hecho.length; i < n; i += 1) {
      pendiente += (i + 1) % MARCA_CADA === 0 ? "╵" : VACIO;
    }
    return { hecho, pendiente };
  }

  function montarBloques(barra) {
    barra.classList.add("blocks");
    barra.replaceChildren(
      crear("span", "blocks__done"),
      crear("span", "blocks__head"),
      crear("span", "blocks__rest"),
      crear("span", "blocks__probe"));
    barra.querySelector(".blocks__head").textContent = "▌";
    barra.querySelector(".blocks__probe").textContent = "█";
  }

  function pintarBloques(barra, fraccion, tipo) {
    const n = columnas(barra);
    const { hecho, pendiente } = textoPista(n, fraccion);
    const lleno = fraccion >= 1;
    barra.querySelector(".blocks__done").textContent = hecho;
    barra.querySelector(".blocks__rest").textContent = pendiente;
    barra.querySelector(".blocks__head").hidden = lleno || fraccion <= 0;
    barra.classList.toggle("bar--full", lleno);
    for (const t of tipos) barra.classList.toggle("blocks--" + t, t === tipo);
  }

  /* ---------------------------- Tira de película --------------------------- */

  function fotograma(datos) {
    const cuadro = crear("span", "film__frame");
    if (datos && IMAGEN_VALIDA.test(datos)) {
      cuadro.style.backgroundImage = `url("${datos}")`;
    } else {
      cuadro.classList.add("film__frame--blank");
    }
    return cuadro;
  }

  // Una tira (negativo o positivo) con un tramo por jornada.
  function tira(jornadas, total, clase) {
    const nodo = crear("span", "film__strip " + clase);
    for (const j of jornadas) {
      const tramo = crear("span", "film__day");
      tramo.style.flexBasis = `${(j.peso / total) * 100}%`;
      const imagenes = [j.primero, j.ultimo ?? j.primero];
      for (let i = 0; i < FOTOGRAMAS_MAX; i += 1) {
        tramo.append(fotograma(imagenes[i % 2]));
      }
      nodo.append(tramo);
    }
    return nodo;
  }

  function montarPelicula(barra, jornadas) {
    const total = jornadas.reduce((suma, j) => suma + j.peso, 0) || 1;
    barra.classList.add("film");
    barra.replaceChildren(
      tira(jornadas, total, "film__strip--neg"),
      tira(jornadas, total, "film__strip--pos"),
      crear("span", "film__gate"));
  }

  function pintarPelicula(barra, fraccion) {
    const pct = Math.min(100, Math.max(0, fraccion * 100));
    barra.querySelector(".film__strip--pos").style.clipPath =
      `inset(0 ${100 - pct}% 0 0)`;
    barra.querySelector(".film__gate").style.left = `${pct}%`;
    barra.classList.toggle("bar--full", fraccion >= 1);
    barra.classList.toggle("film--idle", fraccion <= 0);
  }

  /* -------------------------------- Interfaz ------------------------------- */

  // jornadas: [{peso, primero, ultimo}] de las marcadas, en orden.
  function montar(jornadas) {
    montarBloques(document.getElementById("pr-file-bar"));
    montarBloques(document.getElementById("pr-lote-bar"));
    montarPelicula(document.getElementById("pr-total-bar"), jornadas);
  }

  function pintar(prefijo, fraccion, tipo) {
    const barra = document.getElementById("pr-" + prefijo + "-bar");
    if (barra.classList.contains("film")) pintarPelicula(barra, fraccion);
    else pintarBloques(barra, fraccion, tipo);
  }

  return { montar, pintar, textoPista };
})();
