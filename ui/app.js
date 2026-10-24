(function () {
  const TIPOS = [
    ["jugando", "Jugando", "Jugando a"],
    ["escuchando", "Escuchando", "Escuchando"],
    ["viendo", "Viendo", "Viendo"],
    ["transmitiendo", "Stream", "Transmitiendo"],
    ["compitiendo", "Compitiendo", "Compitiendo en"]
  ];
  const NOMBRE_TIPO = Object.fromEntries(TIPOS.map((t) => [t[0], t[1]]));
  const KICKER = Object.fromEntries(TIPOS.map((t) => [t[0], t[2]]));
  const PUNTOS = [
    ["online", "En línea", "Te ven disponible", "var(--dot-online)"],
    ["idle", "Ausente", "Luna amarilla", "var(--dot-idle)"],
    ["dnd", "No molestar", "Silencia notificaciones", "var(--dot-dnd)"],
    ["invisible", "Invisible", "Apareces desconectado, sin actividad", "var(--dot-invisible)"]
  ];
  const MAX_TEXTO = 128;
  const MAX_ACTIVIDADES = 5;
  const TEMAS = [
    ["pichoni", "Pichoni", "#8b5cf6"],
    ["discord", "Discord", "#5865f2"],
    ["claro", "Claro", "#7650c9"]
  ];
  const AYUDA_TIEMPO = {
    ninguno: "Sin contador en Discord.",
    transcurrido: "Cuenta desde que activas el perfil.",
    fingido: "Discord muestra que ya llevas ese tiempo y sigue contando desde ahí.",
    progreso: "Barra como la de una canción o un video. En Escuchando y Viendo, Discord la muestra como barra.",
    regresiva: "Cuenta hacia atrás desde que activas el perfil."
  };

  let api = null;
  let estado = null;
  let config = null;
  let vista = { tipo: "perfil", id: null };
  let temporizador = null;
  let guardando = false;
  let cambiosSinGuardar = false;
  let preview = null;
  let revision = 0;
  let actualizacion = null;
  let buscandoActualizacion = false;

  const $ = (id) => document.getElementById(id);

  function h(tag, props, ...hijos) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(props || {})) {
      if (v === undefined || v === null || v === false) continue;
      if (k === "class") el.className = v;
      else if (k === "text") el.textContent = v;
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else if (k === "value") el.value = v;
      else if (k === "checked") el.checked = true;
      else el.setAttribute(k, v === true ? "" : v);
    }

    for (const hijo of hijos.flat()) {
      if (hijo === null || hijo === undefined || hijo === false) continue;
      el.append(hijo instanceof Node ? hijo : document.createTextNode(String(hijo)));
    }
    return el;
  }

  function icono(nombre) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("aria-hidden", "true");
    const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", "#i-" + nombre);
    svg.append(use);
    return svg;
  }

  function nuevoId() {
    return (crypto.randomUUID ? crypto.randomUUID() : String(Math.random())).replace(/[^a-z0-9]/gi, "").slice(0, 10);
  }

  function perfilVacio() {
    return {
      id: nuevoId(),
      titulo: "Nuevo perfil",
      tipo: "jugando",
      nombre: "",
      detalles: [""],
      texto: [""],
      rotar_cada: 30,
      url: "",
      imagen: { url: "", texto: "" },
      imagen_chica: { url: "", texto: "" },
      botones: [{ texto: "", url: "" }, { texto: "", url: "" }],
      tiempo: { modo: "ninguno", minutos: 30, total: 60 }
    };
  }

  function perfil(id) {
    return config.perfiles.find((p) => p.id === id) || null;
  }

  function validos(lista) {
    return lista.filter((t) => t.trim());
  }

  function rota(p) {
    return validos(p.detalles).length > 1 || validos(p.texto).length > 1;
  }

  function toast(texto, error) {
    const t = $("toast");
    t.textContent = texto;
    t.classList.toggle("error", !!error);
    t.classList.add("show");
    clearTimeout(toast.t);
    toast.t = setTimeout(() => t.classList.remove("show"), 2800);
  }

  function guardarPronto() {
    cambiosSinGuardar = true;
    clearTimeout(temporizador);
    temporizador = setTimeout(guardarAhora, 500);
  }

  function guardarAhora() {
    clearTimeout(temporizador);
    if (guardando) {
      temporizador = setTimeout(guardarAhora, 200);
      return Promise.resolve();
    }
    guardando = true;
    cambiosSinGuardar = false;
    return api.guardar(config).then((e) => {
      estado = e;
      if (e.config.iniciar_con_windows !== config.iniciar_con_windows) {
        config.iniciar_con_windows = e.config.iniciar_con_windows;
        toast("No se pudo cambiar el inicio con Windows", true);
        if (vista.tipo === "ajustes") pintarContenido();
      }
      pintarCuenta();
      actualizarLimites();
      actualizarPreview();
    }).catch(() => toast("No se pudo guardar", true)).finally(() => { guardando = false; });
  }

  function pintarCuenta() {
    const u = estado && estado.usuario;
    $("usuario").textContent = u ? u.nombre : "Sin conectar";
    if (u && $("avatar").getAttribute("src") !== u.avatar) {
      $("avatar").src = u.avatar;
      $("avatar").alt = "Foto de perfil de " + u.nombre;
    }
    const c = $("conexion");
    const conectado = estado && estado.conectado;
    c.textContent = !estado || !estado.tiene_token ? "Falta el token" : conectado ? "Conectado" : "Conectando…";
    c.classList.toggle("on", !!conectado);
    const punto = PUNTOS.find((x) => x[0] === config.punto);
    $("avatar-dot").style.background = punto ? punto[3] : "var(--dot-invisible)";
    $("insignia-rotacion").classList.toggle("hidden", !config.rotar_perfiles.activo);
    $("banner").classList.toggle("hidden", !(estado && estado.compartir === false && config.perfil_activo));
  }

  function pintarPerfiles() {
    const lista = $("perfiles");
    // Discord only shows one activity per type, so later active profiles of a repeated type stay hidden.
    const tiposVistos = new Set();
    const repetidos = new Set();
    for (const id of config.perfil_activo ? [config.perfil_activo, ...(config.perfiles_extra || [])] : []) {
      const p = perfil(id);
      if (!p) continue;
      if (tiposVistos.has(p.tipo)) repetidos.add(id);
      tiposVistos.add(p.tipo);
    }
    lista.replaceChildren(...config.perfiles.map((p) => {
      const seleccionado = vista.tipo === "perfil" && vista.id === p.id;
      const activo = encendido(p.id);
      const repetido = repetidos.has(p.id);
      return h("li", {},
        h("button", {
          type: "button",
          class: "perfil-item",
          role: "option",
          "aria-selected": seleccionado ? "true" : "false",
          onclick: () => abrir({ tipo: "perfil", id: p.id })
        },
          h("span", { class: "perfil-icono t-" + p.tipo }, icono(p.tipo)),
          h("span", { class: "perfil-texto" },
            h("strong", { text: p.titulo || "Sin título" }),
            h("span", { text: [NOMBRE_TIPO[p.tipo], p.nombre].filter(Boolean).join(" · ") })
          ),
          activo ? h("span", repetido
            ? { class: "en-vivo repetido", role: "img", "aria-label": "Activo pero oculto", title: "Discord muestra uno por tipo. Entra al perfil y pulsa Reemplazar." }
            : { class: "en-vivo", role: "img", "aria-label": "Activo", title: "Activo" }) : null
        )
      );
    }));
    document.querySelectorAll(".nav-item").forEach((b) => {
      if (b.dataset.vista === vista.tipo) b.setAttribute("aria-current", "page");
      else b.removeAttribute("aria-current");
    });
  }

  function abrir(v) {
    vista = v;
    pintarPerfiles();
    pintarContenido();
    $("contenido").scrollTop = 0;
  }

  function barra(titulo, ...acciones) {
    return h("header", { class: "barra" }, h("h1", {}, titulo), ...acciones);
  }

  function seccion(titulo, contenido, pie) {
    return [
      titulo ? h("h2", { class: "seccion-titulo", text: titulo }) : null,
      contenido,
      pie ? h("p", { class: "seccion-pie", text: pie }) : null
    ];
  }

  function fila(etiqueta, control, id) {
    return h("div", { class: "fila" }, h("label", { for: id, text: etiqueta }), control);
  }

  function entrada(props, alCambiar) {
    return h("input", Object.assign({ type: "text", autocomplete: "off", spellcheck: "false" }, props, {
      oninput: (e) => alCambiar(e.target.value)
    }));
  }

  function interruptor(id, marcado, etiqueta, alCambiar) {
    return h("label", { class: "interruptor" },
      h("input", { type: "checkbox", role: "switch", id, checked: marcado, "aria-label": etiqueta, onchange: (e) => alCambiar(e.target.checked) }),
      h("span", {})
    );
  }

  // Steppers for years, days, hours and minutes, all editing one value stored in minutes.
  const UNIDADES = [["anios", 525600, 99, "años"], ["dias", 1440, 364, "d"], ["horas", 60, 23, "h"], ["mins", 1, 59, "min"]];

  function horasMinutos(prefijo, total, alCambiar) {
    let valor = total;
    const parte = (tam, max) => Math.min(max, Math.floor(valor / tam) % (tam === 525600 ? 100 : max + 1));
    return UNIDADES.map(([clave, tam, max, unidad]) => paso(prefijo + "-" + clave, parte(tam, max), 0, max, unidad, (n) => {
      valor = Math.max(1, valor - parte(tam, max) * tam + n * tam);
      alCambiar(valor);
    }));
  }

  function paso(id, valor, min, max, unidad, alCambiar) {
    return h("span", { class: "paso" },
      h("input", {
        type: "number", id, value: valor, min, max, step: 1,
        onchange: (e) => {
          const n = Math.max(min, Math.min(max, parseInt(e.target.value, 10) || min));
          e.target.value = n;
          alCambiar(n);
        }
      }),
      h("span", { text: unidad })
    );
  }

  function segmentado(opciones, actual, etiqueta, alElegir, plano) {
    const grupo = h("div", { class: "segmentado" + (plano ? " plano" : ""), role: "radiogroup", "aria-label": etiqueta });
    const botones = opciones.map(([valor, texto, ico, deshabilitado]) => h("button", {
      type: "button",
      role: "radio",
      disabled: !!deshabilitado,
      "aria-checked": valor === actual ? "true" : "false",
      tabindex: valor === actual ? "0" : "-1",
      onclick: (e) => { if (!e.currentTarget.disabled) alElegir(valor); }
    }, ico ? icono(ico) : null, h("span", { text: texto })));
    grupo.addEventListener("keydown", (e) => {
      const d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
      if (!d) return;
      const habilitados = botones.map((b, i) => b.disabled ? -1 : i).filter((i) => i >= 0);
      const i = habilitados.indexOf(botones.indexOf(document.activeElement));
      if (i < 0 || habilitados.length < 2) return;
      e.preventDefault();
      const j = habilitados[(i + d + habilitados.length) % habilitados.length];
      alElegir(opciones[j][0]);
      requestAnimationFrame(() => {
        const nuevos = document.querySelectorAll('[aria-label="' + etiqueta + '"] button');
        if (nuevos[j]) nuevos[j].focus();
      });
    });
    grupo.append(...botones);
    return grupo;
  }

  function pintarContenido() {
    const cont = $("contenido");
    preview = null;
    if (vista.tipo === "perfil") {
      const p = perfil(vista.id) || config.perfiles[0];
      if (!p) {
        cont.replaceChildren(h("div", { class: "vacio" },
          icono("jugando"),
          h("h2", { text: "Sin perfiles" }),
          h("p", { text: "Crea un perfil para mostrar una actividad en Discord." }),
          h("button", { type: "button", class: "btn btn-primario btn-grande", onclick: crearPerfil }, icono("mas"), "Nuevo perfil")
        ));
        return;
      }
      vista.id = p.id;
      cont.replaceChildren(...vistaPerfil(p));
      avisoStream(p);
      actualizarPreview();
    } else if (vista.tipo === "estado") {
      cont.replaceChildren(...vistaEstado());
    } else if (vista.tipo === "rotacion") {
      cont.replaceChildren(...vistaRotacion());
    } else {
      cont.replaceChildren(...vistaAjustes());
    }
  }

  function encendido(id) {
    return config.perfil_activo === id || (!!config.perfil_activo && (config.perfiles_extra || []).includes(id));
  }

  function perfilesActivos() {
    const ids = config.perfil_activo
      ? [config.perfil_activo, ...(config.perfiles_extra || [])]
      : [];
    const tipos = new Set();
    return ids.map(perfil).filter((p) => {
      if (!p || tipos.has(p.tipo)) return false;
      tipos.add(p.tipo);
      return true;
    });
  }

  function tieneEstadoPersonalizado() {
    return !!(config.personalizado.texto || config.personalizado.emoji);
  }

  function resumenLimiteActividades() {
    const total = perfilesActivos().length + (tieneEstadoPersonalizado() ? 1 : 0);
    return `${total} de ${MAX_ACTIVIDADES} espacios usados. ` +
      (tieneEstadoPersonalizado()
        ? "El estado personalizado ocupa uno; quítalo para usar cinco perfiles a la vez. "
        : "Pichoni puede enviar hasta cinco perfiles de tipos distintos; Discord puede mostrar menos. ") +
      "Discord solo muestra una actividad por tipo; activar otra del mismo tipo reemplaza la anterior.";
  }

  function actualizarLimites() {
    document.querySelectorAll(".limite-actividades").forEach((el) => {
      el.textContent = resumenLimiteActividades();
    });
  }

  function botonActivar(p) {
    const activo = encendido(p.id);
    const oculto = activo && !perfilesActivos().some((x) => x.id === p.id);
    return h("button", {
      type: "button",
      id: "btn-activar",
      class: "btn btn-grande " + (activo && !oculto ? "" : "btn-primario"),
      title: oculto ? "Reemplazar la actividad activa de este tipo" : "Ctrl + Enter",
      onclick: () => (oculto ? activar(p.id) : encendido(p.id) ? apagar(p.id) : activar(p.id))
    }, icono(activo && !oculto ? "stop" : "play"), oculto ? "Reemplazar" : activo ? "Detener" : "Activar");
  }

  function vistaPerfil(p) {
    const titulo = h("input", {
      class: "titulo-editable",
      value: p.titulo,
      maxlength: 40,
      "aria-label": "Nombre del perfil",
      oninput: (e) => { p.titulo = e.target.value; pintarPerfiles(); guardarPronto(); }
    });
    const cabecera = barra(titulo,
      h("button", { type: "button", class: "btn btn-icono", "aria-label": "Duplicar perfil", title: "Duplicar", onclick: () => duplicar(p) }, icono("copiar")),
      h("button", { type: "button", class: "btn btn-icono btn-peligro", "aria-label": "Eliminar perfil", title: "Eliminar", onclick: () => confirmarEliminar(p) }, icono("basura")),
      botonActivar(p)
    );

    const vp = construirPreview();
    const estadoLimite = h("p", { class: "seccion-pie limite-actividades", text: resumenLimiteActividades() });

    const tipo = seccion("Tipo de actividad",
      segmentado(TIPOS.map((t) => [t[0], t[1], t[0]]), p.tipo, "Tipo de actividad", (v) => {
        const conflicto = encendido(p.id)
          ? perfilesActivos().find((x) => x.id !== p.id && x.tipo === v)
          : null;
        if (conflicto) {
          if (config.perfil_activo === conflicto.id) {
            config.perfil_activo = p.id;
            config.perfiles_extra = (config.perfiles_extra || []).filter((id) => {
              const extra = perfil(id);
              return id !== p.id && extra && extra.tipo !== v;
            });
          } else {
            config.perfiles_extra = (config.perfiles_extra || []).filter((id) => id !== conflicto.id);
          }
          if (config.rotar_perfiles.activo && config.rotar_perfiles.ids.includes(conflicto.id)) {
            config.rotar_perfiles.activo = false;
            toast("Reemplacé el perfil del mismo tipo y pausé la rotación", true);
          } else {
            toast("Discord muestra uno por tipo: reemplacé el perfil anterior");
          }
        }
        p.tipo = v;
        if (v === "transmitiendo") p.tiempo.modo = "ninguno";
        guardarPronto();
        pintarPerfiles();
        pintarContenido();
      })
    );

    const general = h("div", { class: "grupo" },
      fila(p.tipo === "escuchando" ? "Qué escuchas" : p.tipo === "viendo" ? "Qué ves" : p.tipo === "transmitiendo" ? "Nombre en la lista" : "Nombre",
        entrada({ id: "f-nombre", value: p.nombre, maxlength: MAX_TEXTO, placeholder: "Minecraft, Spotify, Netflix…" }, (v) => { p.nombre = v; cambio(); pintarPerfiles(); }),
        "f-nombre"),
      p.tipo === "transmitiendo" ? fila("Link del stream (destino de “Ver”)",
        entrada({ id: "f-url", type: "url", value: p.url, maxlength: 512, placeholder: "https://twitch.tv/tucanal" }, (v) => { p.url = v; cambio(); avisoStream(p); }),
        "f-url") : null
    );
    const aviso = h("p", { class: "seccion-pie aviso-stream hidden", id: "aviso-stream", role: "status" },
      "Discord agrega el botón “Ver” automáticamente para las actividades Transmitiendo.");

    const textos = h("div", { class: "grupo", id: "grupo-textos" }, ...listaTextos(p));

    const imagenes = h("div", { class: "imagenes" },
      zonaImagen(p, "imagen", "Imagen grande", false),
      zonaImagen(p, "imagen_chica", "Imagen chica", true)
    );

    const botones = h("div", { class: "grupo" }, ...p.botones.flatMap((b, i) => [
      h("div", { class: "subtitulo-lista", text: "Botón " + (i + 1) }),
      fila("Texto", entrada({ id: "b-texto-" + i, value: b.texto, maxlength: 32, placeholder: i ? "Mi Discord" : "Mi canal" }, (v) => { b.texto = v; cambio(); }), "b-texto-" + i),
      fila("Link", entrada({ id: "b-url-" + i, type: "url", value: b.url, maxlength: 512, placeholder: "https://…" }, (v) => { b.url = v; cambio(); }), "b-url-" + i)
    ]));

    const tiempo = h("div", { class: "grupo" },
      h("div", { class: "fila" }, segmentado([
        ["ninguno", "Sin tiempo"],
        ["transcurrido", "Desde ahora", null, p.tipo === "transmitiendo"],
        ["fingido", "Tiempo fake", null, p.tipo === "transmitiendo"],
        ["progreso", "Barra", null, p.tipo === "transmitiendo"],
        ["regresiva", "Regresiva", null, p.tipo === "transmitiendo"]
      ], p.tiempo.modo, "Tiempo", (v) => {
        p.tiempo.modo = v;
        guardarPronto();
        pintarContenido();
      }, true)),
      p.tiempo.modo === "fingido" || p.tiempo.modo === "progreso" ? h("div", { class: "fila" },
        h("label", { for: "f-horas", text: p.tiempo.modo === "progreso" ? "Ya van" : "Ya llevas" }),
        ...horasMinutos("f", p.tiempo.minutos, (n) => { p.tiempo.minutos = n; cambio(); })
      ) : null,
      p.tiempo.modo === "progreso" ? h("div", { class: "fila" },
        h("label", { for: "t-horas", text: "Dura en total" }),
        ...horasMinutos("t", p.tiempo.total, (n) => { p.tiempo.total = n; cambio(); })
      ) : null,
      p.tiempo.modo === "regresiva" ? h("div", { class: "fila" },
        h("label", { for: "f-horas", text: "Duración" }),
        ...horasMinutos("f", p.tiempo.minutos, (n) => { p.tiempo.minutos = n; cambio(); })
      ) : null
    );

    return [
      cabecera,
      h("div", { class: "pagina" },
        vp,
        estadoLimite,
        ...tipo,
        ...seccion("Actividad", general, p.tipo === "transmitiendo"
          ? "El enlace de Twitch o YouTube es el destino del botón “Ver” obligatorio de Discord. No se puede quitar ni renombrar si mantienes Transmitiendo. Los botones propios se agregan aparte."
          : null),
        p.tipo === "transmitiendo" ? aviso : null,
        ...seccion("Textos", textos, "Agrega varios textos y van cambiando solos. Discord pide mínimo 15 segundos entre cambios."),
        ...seccion("Imágenes", imagenes, "Arrastra una imagen, elígela o pega un link. Las imágenes de tu PC se suben a freeimage.host."),
        ...seccion("Botones", botones, p.tipo === "transmitiendo"
          ? "Puedes agregar hasta 2 botones propios; aparecen además del botón “Ver” obligatorio de Discord."
          : "Hasta 2 botones con link. Tú no los ves en tu perfil, los demás sí."),
        ...seccion("Tiempo", tiempo, p.tipo === "transmitiendo"
          ? "Los streams usan su propio tiempo de emisión; los temporizadores manuales no aplican."
          : AYUDA_TIEMPO[p.tiempo.modo])
      )
    ];
  }

  function listaTextos(p) {
    const partes = [];
    [["detalles", "Primera línea"], ["texto", "Segunda línea"]].forEach(([clave, nombre]) => {
      partes.push(h("div", { class: "subtitulo-lista", text: nombre }));
      p[clave].forEach((valor, i) => {
        const id = "t-" + clave + "-" + i;
        const cuenta = h("span", { class: "contador", text: valor.length + "/" + MAX_TEXTO });
        partes.push(h("div", { class: "fila izq" },
          entrada({ id, value: valor, maxlength: MAX_TEXTO, placeholder: i ? "Otro texto" : "Opcional", "aria-label": nombre + " " + (i + 1) }, (v) => {
            p[clave][i] = v;
            cuenta.textContent = v.length + "/" + MAX_TEXTO;
            cambio();
            pintarRotacionTextos(p);
          }),
          cuenta,
          p[clave].length > 1 ? h("button", {
            type: "button", class: "quitar", "aria-label": "Quitar texto",
            onclick: () => { p[clave].splice(i, 1); guardarPronto(); repintarTextos(p); }
          }, icono("menos")) : null
        ));
      });
      if (p[clave].length < 20) {
        partes.push(h("button", {
          type: "button", class: "agregar",
          onclick: () => {
            p[clave].push("");
            repintarTextos(p);
            const campos = document.querySelectorAll('[id^="t-' + clave + '-"]');
            campos[campos.length - 1].focus();
          }
        }, icono("mas"), "Agregar texto"));
      }
    });
    partes.push(h("div", { class: "fila" + (rota(p) ? "" : " hidden"), id: "fila-rotar" },
      h("label", { for: "f-rotar", text: "Cambiar cada" }),
      paso("f-rotar", p.rotar_cada, 15, 3600, "segundos", (n) => { p.rotar_cada = n; cambio(); })
    ));
    return partes;
  }

  function avisoStream(p) {
    const a = $("aviso-stream");
    if (!a) return;
    const valido = /^https?:\/\/(www\.|m\.)?(twitch\.tv|youtube\.com|youtu\.be)\/\S+/i.test(p.url);
    a.textContent = valido
      ? "Discord agrega el botón “Ver” y usa este enlace como destino. No se puede quitar ni cambiar el texto manteniendo Transmitiendo. Los botones personalizados se muestran aparte."
      : "Para transmitir sin enviar a la gente a un canal genérico, pega un enlace real de Twitch o YouTube: Discord necesita un destino para el botón “Ver”. Sin un enlace válido, Pichoni no publicará este perfil. Los botones personalizados se muestran aparte.";
    a.classList.toggle("hidden", valido && !!p.url);
  }

  function repintarTextos(p) {
    $("grupo-textos").replaceChildren(...listaTextos(p));
    actualizarPreview();
  }

  function pintarRotacionTextos(p) {
    const f = $("fila-rotar");
    if (f) f.classList.toggle("hidden", !rota(p));
  }

  function cambio() {
    guardarPronto();
    actualizarPreview();
  }

  function zonaImagen(p, clave, titulo, circulo) {
    const datos = p[clave];
    const zona = h("div", { class: "zona" });
    const soltar = h("div", {
      class: "soltar" + (circulo ? " circulo" : ""),
      tabindex: "0",
      role: "button",
      "aria-label": titulo + ": elegir o soltar imagen"
    });
    const linkInput = entrada({ id: "img-" + clave, type: "url", value: datos.url, maxlength: 1024, placeholder: "https://…/imagen.png" }, (v) => {
      datos.url = v.trim();
      cambio();
      pintarSoltar();
    });

    function pintarSoltar() {
      soltar.classList.toggle("con-imagen", !!datos.url);
      if (datos.url) {
        const img = h("img", { alt: titulo, referrerpolicy: "no-referrer" });
        img.onerror = () => soltar.replaceChildren(h("div", { class: "soltar-vacio" }, icono("aviso"), h("span", { text: "No se pudo cargar la imagen" })));
        img.src = datos.url;
        soltar.replaceChildren(img);
      } else {
        soltar.replaceChildren(h("div", { class: "soltar-vacio" },
          icono("foto"),
          h("strong", { text: titulo }),
          h("span", { text: "Arrastra aquí o haz clic" })
        ));
      }
      quitar.classList.toggle("hidden", !datos.url);
    }

    function usarUrl(url) {
      datos.url = url;
      linkInput.value = url;
      cambio();
      pintarSoltar();
    }

    function subiendo(promesa) {
      const capa = h("div", { class: "subiendo", text: "Subiendo…" });
      soltar.append(capa);
      return promesa.then((r) => {
        if (r && r.url) { usarUrl(r.url); toast("Imagen lista"); }
        else if (r && r.error) toast(r.error, true);
      }).catch(() => toast("No se pudo subir la imagen", true)).finally(() => capa.remove());
    }

    function elegir() {
      subiendo(api.elegir_archivo());
    }

    function leerArchivo(archivo) {
      if (!/^image\//.test(archivo.type)) { toast("Eso no es una imagen", true); return; }
      if (archivo.size > 10 * 1024 * 1024) { toast("La imagen pesa más de 10 MB", true); return; }
      const lector = new FileReader();
      subiendo(new Promise((ok, mal) => {
        lector.onload = () => api.subir_archivo(archivo.name, lector.result).then(ok, mal);
        lector.onerror = mal;
        lector.readAsDataURL(archivo);
      }));
    }

    soltar.addEventListener("click", elegir);
    soltar.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); elegir(); } });
    soltar.addEventListener("dragover", (e) => { e.preventDefault(); soltar.classList.add("encima"); });
    soltar.addEventListener("dragleave", () => soltar.classList.remove("encima"));
    soltar.addEventListener("drop", (e) => {
      e.preventDefault();
      e.stopPropagation();
      soltar.classList.remove("encima");
      const archivo = e.dataTransfer.files && e.dataTransfer.files[0];
      if (archivo) { leerArchivo(archivo); return; }
      const url = (e.dataTransfer.getData("text/uri-list") || e.dataTransfer.getData("text/plain") || "").split("\n")[0].trim();
      if (/^https?:\/\//.test(url)) usarUrl(url);
    });

    const quitar = h("button", { type: "button", class: "btn btn-peligro", onclick: () => usarUrl("") }, "Quitar");
    zona.append(
      soltar,
      h("div", { class: "zona-acciones" }, h("button", { type: "button", class: "btn", onclick: elegir }, "Elegir…"), quitar),
      h("div", { class: "fila" }, h("label", { for: "img-" + clave, text: "Link" }), linkInput),
      h("div", { class: "fila" }, h("label", { for: "txt-" + clave, text: "Texto" }),
        entrada({ id: "txt-" + clave, value: datos.texto, maxlength: MAX_TEXTO, placeholder: "Al pasar el mouse" }, (v) => { datos.texto = v; cambio(); }))
    );
    pintarSoltar();
    return zona;
  }

  function construirPreview() {
    const partes = {
      kicker: h("span", {}),
      rot: h("span", { class: "vp-rot hidden" }, icono("rotacion"), h("span", {})),
      personal: h("div", { class: "vp-personal hidden" }),
      grande: h("div", { class: "vp-grande" }),
      chica: h("div", { class: "vp-chica hidden" }),
      nombre: h("strong", {}),
      detalles: h("span", {}),
      texto: h("span", {}),
      tiempo: h("span", { class: "vp-tiempo" }),
      barra: h("div", { class: "vp-barra hidden" }, h("span", {})),
      botones: h("div", { class: "vp-botones" }),
      estado: h("div", { class: "vp-estado" })
    };
    preview = partes;
    return h("section", { class: "vista-previa", "aria-label": "Vista previa en Discord" },
      h("div", { class: "vp-encabezado" },
        h("span", { class: "vp-marca", text: "DISCORD" }),
        h("span", { class: "vp-etiqueta", text: "VISTA PREVIA" })
      ),
      partes.personal,
      h("p", { class: "vp-kicker" }, partes.kicker, partes.rot),
      h("div", { class: "vp-cuerpo" },
        h("div", { class: "vp-arte" }, partes.grande, partes.chica),
        h("div", { class: "vp-meta" }, partes.nombre, partes.detalles, partes.texto, partes.barra, partes.tiempo)
      ),
      partes.botones,
      partes.estado,
      h("p", {
        class: "vp-nota",
        text: "Vista aproximada: Discord puede mostrarla distinto según el cliente y la privacidad de la cuenta."
      })
    );
  }

  function ponerImagen(caja, url, respaldo) {
    if (caja.dataset.url === (url || "")) return;
    caja.dataset.url = url || "";
    if (url) {
      const img = h("img", { alt: "", referrerpolicy: "no-referrer" });
      img.onerror = () => caja.replaceChildren(respaldo ? icono(respaldo) : "");
      img.src = url;
      caja.replaceChildren(img);
    } else {
      caja.replaceChildren(respaldo ? icono(respaldo) : "");
    }
  }

  function formatoTiempo(ms) {
    const s = Math.max(0, Math.floor(ms / 1000));
    const hh = Math.floor(s / 3600);
    const mm = String(Math.floor((s % 3600) / 60)).padStart(2, "0");
    const ss = String(s % 60).padStart(2, "0");
    return (hh ? hh + ":" : "") + mm + ":" + ss;
  }

  function actualizarPreview() {
    if (!preview || vista.tipo !== "perfil") return;
    const p = perfil(vista.id);
    if (!p) return;
    const activo = encendido(p.id);
    const indice = activo && estado ? estado.indice : Math.floor(Date.now() / 1000 / Math.max(15, p.rotar_cada));
    const elegir = (lista) => { const v = validos(lista); return v.length ? v[indice % v.length] : ""; };

    const per = config.personalizado;
    preview.personal.classList.toggle("hidden", !per.texto && !per.emoji);
    preview.personal.textContent = [per.emoji, per.texto].filter(Boolean).join(" ");

    preview.kicker.textContent = KICKER[p.tipo];
    preview.rot.classList.toggle("hidden", !rota(p));
    preview.rot.lastChild.textContent = "cada " + p.rotar_cada + " s";
    ponerImagen(preview.grande, p.imagen.url, p.tipo);
    preview.grande.title = p.imagen.texto || "";
    preview.chica.classList.toggle("hidden", !p.imagen_chica.url);
    ponerImagen(preview.chica, p.imagen_chica.url, null);
    preview.chica.title = p.imagen_chica.texto || "";
    const nombre = p.nombre || p.titulo || "Discord";
    const lineas = p.tipo === "transmitiendo"
      ? [elegir(p.detalles) || nombre, elegir(p.texto), p.imagen.url ? p.imagen.texto : ""]
      : [nombre, elegir(p.detalles), elegir(p.texto)];
    preview.nombre.textContent = lineas[0];
    preview.detalles.textContent = lineas[1];
    preview.texto.textContent = lineas[2];

    const inicio = activo && estado && estado.inicio ? estado.inicio * 1000 : Date.now();
    let tiempo = "";
    if (p.tipo !== "transmitiendo" && p.tiempo.modo === "transcurrido") tiempo = formatoTiempo(Date.now() - inicio) + " transcurrido";
    if (p.tipo !== "transmitiendo" && p.tiempo.modo === "fingido") tiempo = formatoTiempo(Date.now() - inicio + p.tiempo.minutos * 60000) + " transcurrido";
    if (p.tipo !== "transmitiendo" && p.tiempo.modo === "regresiva") tiempo = "Quedan " + formatoTiempo(inicio + p.tiempo.minutos * 60000 - Date.now());
    const enBarra = p.tipo !== "transmitiendo" && p.tiempo.modo === "progreso";
    if (enBarra) {
      const total = Math.max(p.tiempo.total, p.tiempo.minutos + 1) * 60000;
      const va = Math.min(total, Date.now() - inicio + p.tiempo.minutos * 60000);
      tiempo = formatoTiempo(va) + " / " + formatoTiempo(total);
      preview.barra.firstChild.style.width = (va / total * 100).toFixed(2) + "%";
    }
    preview.barra.classList.toggle("hidden", !enBarra);
    preview.tiempo.textContent = tiempo;

    const botones = [];
    if (p.tipo === "transmitiendo" &&
        /^https?:\/\/(www\.|m\.)?(twitch\.tv|youtube\.com|youtu\.be)\/\S+/i.test(p.url)) {
      botones.push(["Ver", "stream", p.url]);
    }
    p.botones.forEach((b) => { if (b.texto && /^https?:\/\//.test(b.url)) botones.push([b.texto, "", b.url]); });
    const firma = JSON.stringify(botones);
    if (preview.botones.dataset.firma !== firma) {
      preview.botones.dataset.firma = firma;
      preview.botones.replaceChildren(...botones.map(([t, c, url]) => h("span", { class: c, text: t, title: url || undefined })));
    }

    let clase = "vp-estado";
    let texto = "No está activo";
    let ico = null;
    if (p.tipo === "transmitiendo" &&
        !/^https?:\/\/(www\.|m\.)?(twitch\.tv|youtube\.com|youtu\.be)\/\S+/i.test(p.url)) {
      clase += " mal";
      texto = "No se envía: falta un enlace real de Twitch o YouTube";
      ico = "aviso";
    } else if (activo) {
      if (!estado || !estado.conectado) texto = "Conectando con Discord…";
      else if (estado.visible === true) { clase += " ok"; texto = "Visible en Discord"; ico = "check"; }
      else if (estado.visible === false) { clase += " mal"; texto = "Discord la está ocultando"; ico = "aviso"; }
      else texto = "Comprobando…";
    }
    preview.estado.className = clase;
    const omitidas = estado && estado.actividades_omitidas || 0;
    const estadoHijos = [ico ? icono(ico) : null, h("span", { text: texto })].filter(Boolean);
    if (omitidas) estadoHijos.push(h("span", {
        class: "vp-nota-omitidas",
        text: `Discord no muestra ${omitidas} perfil(es): falta enlace de stream, repiten tipo o exceden su límite.`
    }));
    preview.estado.replaceChildren(...estadoHijos);
  }

  function vistaEstado() {
    const opciones = h("div", { class: "grupo", role: "radiogroup", "aria-label": "Disponibilidad" },
      ...PUNTOS.map(([valor, nombre, desc, color]) => h("button", {
        type: "button",
        class: "fila opcion",
        role: "radio",
        "aria-checked": config.punto === valor ? "true" : "false",
        onclick: () => { config.punto = valor; guardarPronto(); pintarCuenta(); pintarContenido(); }
      },
        h("span", { class: "punto", style: "background:" + color }),
        h("span", { class: "opcion-texto" }, h("span", { text: nombre }), h("small", { text: desc })),
        h("span", { class: "marca" }, icono("check"))
      ))
    );
    const per = config.personalizado;
    const cambiarPersonalizado = (clave, valor) => {
      const nuevoValor = valor.trim();
      if (nuevoValor && !tieneEstadoPersonalizado() && perfilesActivos().length >= MAX_ACTIVIDADES) {
        $("p-" + clave).value = per[clave];
        toast("Ya hay cinco perfiles activos. Detén uno antes de añadir un estado personalizado.", true);
        return;
      }
      per[clave] = nuevoValor;
      actualizarLimites();
      guardarPronto();
    };
    const personal = h("div", { class: "grupo" },
      fila("Emoji", entrada({ id: "p-emoji", value: per.emoji, maxlength: 16, placeholder: "🔥" }, (v) => cambiarPersonalizado("emoji", v)), "p-emoji"),
      fila("Texto", entrada({ id: "p-texto", value: per.texto, maxlength: MAX_TEXTO, placeholder: "¿Qué estás haciendo?" }, (v) => cambiarPersonalizado("texto", v)), "p-texto")
    );
    const activo = perfil(config.perfil_activo);
    const activos = config.perfiles.filter((x) => encendido(x.id)).map((x) => x.titulo);
    const limiteActividades = h("p", { class: "seccion-pie limite-actividades", text: resumenLimiteActividades() });
    const actual = h("div", { class: "grupo" },
      h("div", { class: "fila" },
        h("span", { class: "etiqueta" }, "Actividad", h("small", { text: activos.length ? activos.join(", ") : "Ninguna" })),
        activo ? h("button", { type: "button", class: "btn btn-chico", style: "margin-left:auto", onclick: detener }, "Detener") : null
      ),
      h("div", { class: "fila" },
        h("span", { class: "etiqueta" }, "Compartir actividad", h("small", {
          text: estado && estado.compartir === false ? "Apagado: Discord oculta tu actividad" : estado && estado.compartir ? "Encendido" : "Sin revisar"
        })),
        estado && estado.compartir === false ? h("button", { type: "button", class: "btn btn-primario btn-chico", style: "margin-left:auto", onclick: activarCompartir }, "Activar") : null
      )
    );
    return [
      barra(h("span", { text: "Estado" })),
      h("div", { class: "pagina" },
        ...seccion("Disponibilidad", opciones),
        ...seccion("Estado personalizado", personal, "Sale junto a la actividad y ocupa uno de los cinco espacios de Discord. Win + . abre el selector de emojis de Windows."),
        limiteActividades,
        ...seccion("Ahora", actual, estado && estado.actividades_omitidas
          ? `Discord no está mostrando ${estado.actividades_omitidas} perfil(es): falta enlace de stream, repiten tipo o exceden el límite de actividades.`
          : null)
      )
    ];
  }

  function vistaRotacion() {
    const r = config.rotar_perfiles;
    const general = h("div", { class: "grupo" },
      h("div", { class: "fila" },
        h("span", { class: "etiqueta" }, "Rotar perfiles", h("small", { text: "Cambia de perfil automáticamente" })),
        interruptor("f-rotar-on", r.activo, "Rotar perfiles", (v) => {
          if (v && r.ids.length < 2) {
            toast("Marca al menos 2 perfiles", true);
            pintarContenido();
            return;
          }
          r.activo = v;
          if (v && !r.ids.includes(config.perfil_activo)) config.perfil_activo = r.ids[0];
          guardarAhora();
          pintarCuenta();
          pintarPerfiles();
        })
      ),
      h("div", { class: "fila" },
        h("label", { for: "f-rot-min", text: "Cambiar cada" }),
        paso("f-rot-min", r.minutos, 1, 1440, "minutos", (n) => { r.minutos = n; guardarPronto(); })
      )
    );
    const lista = h("div", { class: "grupo" }, ...config.perfiles.map((p) => h("label", { class: "fila", for: "rot-" + p.id },
      h("input", {
        type: "checkbox", class: "check-cuadro", id: "rot-" + p.id, checked: r.ids.includes(p.id),
        onchange: (e) => {
          if (e.target.checked) r.ids = config.perfiles.map((x) => x.id).filter((id) => id === p.id || r.ids.includes(id));
          else r.ids = r.ids.filter((id) => id !== p.id);
          if (r.activo && r.ids.length < 2) { r.activo = false; toast("Rotación apagada: quedan menos de 2 perfiles"); pintarContenido(); }
          guardarPronto();
          pintarCuenta();
        }
      }),
      h("span", { class: "perfil-icono t-" + p.tipo }, icono(p.tipo)),
      h("span", { class: "perfil-texto" }, h("strong", { text: p.titulo }), h("span", { text: NOMBRE_TIPO[p.tipo] }))
    )));
    return [
      barra(h("span", { text: "Rotación" })),
      h("div", { class: "pagina" },
        ...seccion(null, general),
        ...seccion("Perfiles en la rotación", config.perfiles.length ? lista : h("p", { class: "seccion-pie", text: "Todavía no hay perfiles." }), "Van en el orden de la barra lateral. Los textos de cada perfil siguen rotando igual.")
      )
    ];
  }

  function vistaAjustes() {
    const selectorTema = h("div", { class: "temas", role: "radiogroup", "aria-label": "Tema de color" },
      ...TEMAS.map(([id, nombre, color]) => h("button", {
        type: "button",
        class: "tema-opcion",
        role: "radio",
        "aria-checked": config.tema === id ? "true" : "false",
        onclick: () => {
          config.tema = id;
          aplicarTema(id);
          guardarPronto();
          pintarContenido();
        }
      },
        h("span", { class: "tema-muestra", style: `--tema-muestra:${color}` }),
        h("span", { text: nombre })
      ))
    );
    const estadoActualizacion = !actualizacion
      ? "Busca una versión nueva de Pichoni."
      : actualizacion.estado === "buscando"
        ? "Consultando versiones publicadas…"
        : actualizacion.estado === "disponible"
          ? `Hay una versión nueva (${actualizacion.disponible}).`
          : actualizacion.estado === "actualizada"
            ? `Estás al día (${actualizacion.actual}).`
            : actualizacion.estado === "sin_versiones"
              ? "Todavía no hay versiones publicadas."
              : "No se pudo comprobar. Revisa tu conexión e inténtalo otra vez.";
    const actualizaciones = h("div", { class: "actualizacion" },
      h("div", { class: "actualizacion-info" },
        h("strong", { text: "Pichoni " + (actualizacion?.actual || "") }),
        h("small", { text: estadoActualizacion })
      ),
      h("div", { class: "actualizacion-acciones" },
        h("button", {
          type: "button",
          class: "btn btn-chico",
          disabled: buscandoActualizacion,
          onclick: buscarActualizaciones
        }, buscandoActualizacion ? "Buscando…" : "Buscar actualizaciones"),
        actualizacion?.estado === "disponible" || actualizacion?.estado === "sin_versiones"
          ? h("button", {
            type: "button",
            class: "btn btn-chico btn-primario",
            onclick: async () => {
                if (!await api.abrir_pagina_descargas(actualizacion.url)) toast("No se pudo abrir la página de versiones", true);
            }
          }, actualizacion.estado === "disponible" ? "Descargar" : "Ver versiones")
          : null
      )
    );
    const cuenta = h("div", { class: "grupo" },
      h("div", { class: "fila" },
        h("span", { class: "etiqueta" }, "Cuenta", h("small", { text: estado && estado.usuario ? "@" + estado.usuario.tag : "Sin conectar" })),
        h("button", { type: "button", class: "btn btn-chico", style: "margin-left:auto", onclick: hojaToken }, "Cambiar token"),
        h("button", { type: "button", class: "btn btn-chico btn-peligro", onclick: cerrarSesion }, icono("salir"), "Cerrar sesión")
      ),
      h("div", { class: "fila" },
        h("span", { class: "etiqueta" }, "Iniciar con Windows", h("small", { text: "Se abre sola, minimizada en la bandeja" })),
        interruptor("f-inicio", config.iniciar_con_windows, "Iniciar con Windows", (v) => { config.iniciar_con_windows = v; guardarAhora(); })
      )
    );
    const avanzado = h("div", { class: "grupo" },
      fila("Application ID", entrada({ id: "f-app", value: config.app_id, maxlength: 24, placeholder: "383226320970055681", inputmode: "numeric" }, (v) => {
        if (/^\d{15,24}$/.test(v.trim())) { config.app_id = v.trim(); guardarPronto(); }
      }), "f-app")
    );
    const tema = h("div", { class: "grupo" }, selectorTema);
    return [
      barra(h("span", { text: "Ajustes" })),
      h("div", { class: "pagina" },
        ...seccion(null, cuenta, "Al cerrar la ventana la app sigue en la bandeja, junto al reloj. Para salir usa clic derecho en su ícono."),
        ...seccion("Apariencia", tema, "El tema se guarda en este PC y puedes cambiarlo cuando quieras."),
        ...seccion("Avanzado", avanzado, "Discord necesita una app para mostrar imágenes y botones. Si aparece el nombre de otra app, crea la tuya en discord.com/developers y pega su ID."),
        ...seccion("Actualizaciones", actualizaciones, "Consulta las versiones y descarga el instalador oficial de Pichoni."),
        ...seccion("Aviso", h("div", { class: "grupo" }, h("div", { class: "fila" }, h("span", {
          text: "Esta app usa tu cuenta directamente. Va contra las reglas de Discord y existe riesgo de baneo. Nunca compartas tu token."
        }))))
      )
    ];
  }

  function hoja(...hijos) {
    $("hoja").replaceChildren(...hijos);
    $("velo").classList.remove("hidden");
    const foco = $("hoja").querySelector("input, button.btn-primario, button");
    if (foco) foco.focus();
  }

  function cerrarHoja() {
    $("velo").classList.add("hidden");
  }

  function hojaToken() {
    const campo = h("input", { class: "campo", type: "password", placeholder: "Pega tu nuevo token", autocomplete: "off", "aria-label": "Token de Discord" });
    const error = h("p", { class: "error", role: "alert" });
    const boton = h("button", { type: "button", class: "btn btn-primario" }, "Guardar");
    const enviar = () => {
      boton.disabled = true;
      error.textContent = "";
      api.guardar_token(campo.value).then((r) => {
        if (r.error) { error.textContent = r.error; return; }
        estado = r;
        cerrarHoja();
        pintarCuenta();
        toast("Cuenta conectada");
      }).finally(() => { boton.disabled = false; });
    };
    boton.addEventListener("click", enviar);
    campo.addEventListener("keydown", (e) => { if (e.key === "Enter") enviar(); });
    hoja(
      h("h2", { id: "hoja-titulo", text: "Cambiar token" }),
      h("p", { text: "Se reemplaza el token guardado en este PC." }),
      campo,
      error,
      h("div", { class: "acciones" }, h("button", { type: "button", class: "btn", onclick: cerrarHoja }, "Cancelar"), boton)
    );
  }

  function mostrarBienvenida(visible) {
    $("bienvenida").classList.toggle("hidden", !visible);
    $("app").classList.toggle("hidden", visible);
    if (visible) {
      cerrarHoja();
      setTimeout(() => $("token-inicio").focus(), 50);
    }
  }

  function aplicarTema(tema) {
    document.documentElement.dataset.theme = TEMAS.some(([id]) => id === tema) ? tema : "pichoni";
  }

  async function buscarActualizaciones() {
    buscandoActualizacion = true;
    actualizacion = { estado: "buscando" };
    pintarContenido();
    try {
      actualizacion = await api.comprobar_actualizacion();
    } catch {
      actualizacion = { estado: "error" };
    } finally {
      buscandoActualizacion = false;
      if (vista.tipo === "ajustes") pintarContenido();
    }
  }

  let animandoSalida = false;

  function iniciarAnimacionApertura() {
    if (animandoSalida) return;
    const splash = $("splash");
    if (!splash) return;
    splash.classList.remove("terminado", "cerrando");
    splash.classList.add("visible", "entrando");
    window.clearTimeout(iniciarAnimacionApertura.temporizador);
    iniciarAnimacionApertura.temporizador = window.setTimeout(() => {
      splash.classList.remove("visible", "entrando");
      splash.classList.add("terminado");
    }, 950);
  }

  function iniciarAnimacionCierre() {
    if (animandoSalida) return;
    animandoSalida = true;
    const splash = $("splash");
    if (splash) {
      splash.classList.remove("terminado", "entrando");
      splash.classList.add("cerrando");
    }
    $("app").classList.add("saliendo");
    window.setTimeout(() => {
      if (api) api.cerrar();
    }, 650);
  }

  window.iniciarAnimacionApertura = iniciarAnimacionApertura;
  window.iniciarAnimacionCierre = iniciarAnimacionCierre;
  window.setTimeout(() => {
    const splash = $("splash");
    if (splash && !splash.classList.contains("terminado")) {
      splash.classList.remove("visible", "entrando");
      splash.classList.add("terminado");
    }
  }, 1200);

  function conectarInicio() {
    const boton = $("token-conectar");
    const campo = $("token-inicio");
    boton.disabled = true;
    boton.textContent = "Conectando…";
    $("token-error").textContent = "";
    api.guardar_token(campo.value).then((r) => {
      if (r.error) { $("token-error").textContent = r.error; return; }
      campo.value = "";
      arrancar(r);
      toast("Cuenta conectada");
    }).catch(() => { $("token-error").textContent = "No se pudo conectar. Revisa tu internet."; })
      .finally(() => { boton.disabled = false; boton.textContent = "Conectar"; });
  }

  function cerrarSesion() {
    hoja(
      h("h2", { id: "hoja-titulo", text: "¿Cerrar sesión?" }),
      h("p", { text: "Se borra el token de este PC y se quita tu actividad. Tus perfiles se mantienen." }),
      h("div", { class: "acciones" },
        h("button", { type: "button", class: "btn", onclick: cerrarHoja }, "Cancelar"),
        h("button", { type: "button", class: "btn btn-primario", style: "background:var(--red-cerrar)", onclick: () => {
          api.borrar_token().then((e) => { estado = e; mostrarBienvenida(true); pintarCuenta(); });
        } }, "Cerrar sesión")
      )
    );
  }

  function confirmarEliminar(p) {
    hoja(
      h("h2", { id: "hoja-titulo", text: "¿Eliminar \"" + (p.titulo || "Sin título") + "\"?" }),
      h("p", { text: "Esta acción no se puede deshacer." }),
      h("div", { class: "acciones" },
        h("button", { type: "button", class: "btn", onclick: cerrarHoja }, "Cancelar"),
        h("button", { type: "button", class: "btn btn-primario", style: "background:var(--red)", onclick: () => { cerrarHoja(); eliminar(p); } }, "Eliminar")
      )
    );
  }

  function crearPerfil() {
    const p = perfilVacio();
    config.perfiles.push(p);
    guardarAhora();
    abrir({ tipo: "perfil", id: p.id });
    const t = document.querySelector(".titulo-editable");
    if (t) { t.focus(); t.select(); }
  }

  function duplicar(p) {
    const copia = JSON.parse(JSON.stringify(p));
    copia.id = nuevoId();
    copia.titulo = (p.titulo + " copia").slice(0, 40);
    config.perfiles.splice(config.perfiles.indexOf(p) + 1, 0, copia);
    guardarAhora();
    abrir({ tipo: "perfil", id: copia.id });
    toast("Perfil duplicado");
  }

  function eliminar(p) {
    const i = config.perfiles.indexOf(p);
    config.perfiles.splice(i, 1);
    config.rotar_perfiles.ids = config.rotar_perfiles.ids.filter((id) => id !== p.id);
    if (config.rotar_perfiles.ids.length < 2) config.rotar_perfiles.activo = false;
    config.perfiles_extra = (config.perfiles_extra || []).filter((id) => id !== p.id);
    if (config.perfil_activo === p.id) config.perfil_activo = null;
    guardarAhora();
    const siguiente = config.perfiles[Math.min(i, config.perfiles.length - 1)];
    abrir({ tipo: "perfil", id: siguiente ? siguiente.id : null });
    pintarCuenta();
  }

  function refrescarActivos() {
    pintarPerfiles();
    pintarCuenta();
    if (vista.tipo === "perfil") pintarContenido();
  }

  function activar(id) {
    const seleccionado = perfil(id);
    if (!seleccionado) return;
    if (seleccionado.tipo === "transmitiendo" &&
        !/^https?:\/\/(www\.|m\.)?(twitch\.tv|youtube\.com|youtu\.be)\/\S+/i.test(seleccionado.url)) {
      toast("Agrega un enlace real de Twitch o YouTube para activar Transmitiendo.", true);
      return;
    }
    const activos = perfilesActivos();
    const tipoRepetido = activos.find((p) => p.id !== id && p.tipo === seleccionado.tipo);
    if (tipoRepetido) {
      if (config.perfil_activo === tipoRepetido.id) {
        config.perfil_activo = id;
        config.perfiles_extra = (config.perfiles_extra || []).filter((x) => {
          const extra = perfil(x);
          return x !== id && extra && extra.tipo !== seleccionado.tipo;
        });
      } else {
        config.perfiles_extra = [
          ...(config.perfiles_extra || []).filter((x) => {
            const extra = perfil(x);
            return x !== id && extra && extra.tipo !== seleccionado.tipo;
          }),
          id
        ];
      }
      if (config.rotar_perfiles.activo && !config.rotar_perfiles.ids.includes(id)) {
        config.rotar_perfiles.activo = false;
      }
      guardarAhora().then(() => toast("Discord muestra uno por tipo: reemplacé el perfil anterior"));
      refrescarActivos();
      return;
    }
    const limitePerfiles = MAX_ACTIVIDADES - (tieneEstadoPersonalizado() ? 1 : 0);
    if (activos.length >= limitePerfiles) {
      toast(tieneEstadoPersonalizado()
        ? "El estado personalizado ocupa un espacio. Quítalo para activar cinco perfiles."
        : "Ya están ocupados los cinco espacios de actividad de Discord.", true);
      return;
    }
    if (config.perfil_activo && config.perfil_activo !== id) {
      config.perfiles_extra = (config.perfiles_extra || []).filter((x) => x !== id).concat(id);
      guardarAhora().then(() => toast("Perfil sumado"));
      refrescarActivos();
      return;
    }
    config.perfil_activo = id;
    if (config.rotar_perfiles.activo && !config.rotar_perfiles.ids.includes(id)) {
      config.rotar_perfiles.activo = false;
      toast("Rotación pausada: este perfil no está en ella");
    }
    guardarAhora().then(() => toast("Perfil activado"));
    pintarPerfiles();
    pintarCuenta();
    if (vista.tipo === "perfil") {
      const viejo = $("btn-activar");
      if (viejo) viejo.replaceWith(botonActivar(perfil(vista.id)));
      actualizarPreview();
    }
  }

  function apagar(id) {
    const extras = config.perfiles_extra || [];
    if (config.perfil_activo === id && extras.length && !config.rotar_perfiles.activo) {
      config.perfil_activo = extras[0];
      config.perfiles_extra = extras.slice(1);
    } else if (config.perfil_activo !== id) {
      config.perfiles_extra = extras.filter((x) => x !== id);
    } else {
      detener();
      return;
    }
    guardarAhora().then(() => toast("Perfil detenido"));
    refrescarActivos();
  }

  function detener() {
    config.perfil_activo = null;
    config.rotar_perfiles.activo = false;
    guardarAhora().then(() => toast("Actividad quitada"));
    pintarPerfiles();
    pintarCuenta();
    pintarContenido();
  }

  function activarCompartir() {
    api.activar_compartir().then((r) => {
      if (r.ok) {
        estado.compartir = true;
        toast("Compartir actividad activado");
        pintarCuenta();
        if (vista.tipo === "estado") pintarContenido();
      } else toast("No se pudo activar", true);
    });
  }

  function refrescar() {
    api.estado().then((e) => {
      const antes = config.perfil_activo;
      estado = e;
      if (e.revision !== revision && !guardando && !cambiosSinGuardar && !document.activeElement.matches("input")) {
        revision = e.revision;
        config = e.config;
        aplicarTema(config.tema);
        pintarPerfiles();
        pintarContenido();
      }
      if (!guardando && !cambiosSinGuardar && e.config.perfil_activo !== antes) {
        config.perfil_activo = e.config.perfil_activo;
        pintarPerfiles();
        if (vista.tipo === "perfil") {
          const b = $("btn-activar");
          if (b) b.replaceWith(botonActivar(perfil(vista.id)));
        }
      }
      pintarCuenta();
      actualizarPreview();
      if (!e.tiene_token && $("bienvenida").classList.contains("hidden")) mostrarBienvenida(true);
    }).catch(() => {});
  }

  let arrancado = false;

  function arrancar(e) {
    estado = e;
    config = e.config;
    aplicarTema(config.tema);
    revision = e.revision;
    mostrarBienvenida(false);
    vista = { tipo: "perfil", id: config.perfil_activo || (config.perfiles[0] && config.perfiles[0].id) };
    pintarCuenta();
    abrir(vista);
    if (!arrancado) {
      arrancado = true;
      setInterval(refrescar, 1500);
      setInterval(actualizarPreview, 1000);
    }
  }

  function iniciar() {
    api = window.pywebview.api;
    api.estado().then((e) => {
      aplicarTema(e.config.tema);
      if (e.tiene_token) arrancar(e);
      else { estado = e; config = e.config; mostrarBienvenida(true); }
    });
  }

  function pintarMaximizado(max) {
    const b = $("c-max");
    b.replaceChildren(icono(max ? "rest" : "max"));
    b.setAttribute("aria-label", max ? "Restaurar" : "Maximizar");
    b.title = max ? "Restaurar" : "Maximizar";
  }

  $("c-min").addEventListener("click", () => api && api.minimizar());
  $("c-max").addEventListener("click", () => api && api.maximizar().then(pintarMaximizado));
  $("c-cerrar").addEventListener("click", iniciarAnimacionCierre);
  $("arrastre").addEventListener("dblclick", () => api && api.maximizar().then(pintarMaximizado));
  $("token-conectar").addEventListener("click", conectarInicio);
  $("token-inicio").addEventListener("keydown", (e) => { if (e.key === "Enter") conectarInicio(); });
  $("token-ojo").addEventListener("click", () => {
    const c = $("token-inicio");
    const ver = c.type === "password";
    c.type = ver ? "text" : "password";
    $("token-ojo").setAttribute("aria-label", ver ? "Ocultar token" : "Mostrar token");
    c.focus();
  });

  document.querySelectorAll(".nav-item").forEach((b) => b.addEventListener("click", () => abrir({ tipo: b.dataset.vista })));
  $("nuevo-perfil").addEventListener("click", crearPerfil);
  $("banner-activar").addEventListener("click", activarCompartir);
  $("contenido").addEventListener("scroll", (e) => {
    const b = e.target.querySelector(".barra");
    if (b) b.classList.toggle("sombra", e.target.scrollTop > 4);
  });
  $("velo").addEventListener("click", (e) => { if (e.target === $("velo")) cerrarHoja(); });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !$("velo").classList.contains("hidden")) cerrarHoja();
    if (!$("bienvenida").classList.contains("hidden")) return;
    if (e.ctrlKey && e.key.toLowerCase() === "n") { e.preventDefault(); crearPerfil(); }
    if (e.ctrlKey && e.key === "Enter" && vista.tipo === "perfil" && vista.id) {
      e.preventDefault();
      if (encendido(vista.id)) apagar(vista.id); else activar(vista.id);
    }
  });
  window.addEventListener("dragover", (e) => e.preventDefault());
  window.addEventListener("drop", (e) => e.preventDefault());

  if (window.pywebview && window.pywebview.api && window.pywebview.api.estado) iniciar();
  else window.addEventListener("pywebviewready", iniciar);
})();
