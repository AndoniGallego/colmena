use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::mpsc::{channel, Receiver, RecvTimeoutError, Sender};
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant};

use colmena_nucleo::config::ConfigNudo;
use colmena_nucleo::nudo::controles::{limpiar_nombre, ControlListado};
use colmena_nucleo::nudo::coords::{a_overlay, origen_nudo, Lado, RectLogico};
use colmena_nucleo::nudo::guia::{acotar_paso, atajo_guia, globo_guia, AccionGuia, AtajoGuia, GloboGuia, PasoGuia};
use colmena_nucleo::nudo::imagen::{codificar, ImagenCodificada, TOPE_IMAGEN};
use colmena_nucleo::nudo::orden::{
    validar_espera, validar_marcas, validar_texto, Marca, SESION_MAX, TEXTO_MAX,
};
use colmena_nucleo::nudo::salida::{ocultar_tras_salida, SALIDA_MS};
use colmena_nucleo::nudo::visible::Cambio;
use colmena_nucleo::nudo::pc::{
    codigo_de_error, indice_en_foto, monitor_para, popup_nuevo_pegado, texto_marcas, texto_monitor, Guardada,
};
use colmena_nucleo::nudo::zonas::{
    captura_vigente, misma_ventana, recorte_captura, tam_imagen, validar_zona, validar_zonas, zona_a_fisico, Captura,
    ZonaEtiquetada, ZonaImagen, LADO_MAX_IMAGEN,
};
use colmena_nucleo::nudo::{ERR_APAGADO, ERR_FALLO_PC, ERR_FOTO_VIEJA, ERR_SIN_VENTANA};
use colmena_nucleo::posicion::Rect;
use colmena_nucleo::validar::es_url_local;
use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager, Monitor, State, WebviewWindow};

use crate::captura::capturar_bgra;
use crate::uia::HiloUia;
use crate::{exige_ventana, ventanas, Estado};

// Los eventos no llevan datos: son solo el aviso de "cambió". Las páginas piden el estado
// con `nudo_pagina_estado`, que solo permiten las capabilities locales (un emit del notch remoto no inyecta nada).
pub const EVENTO_DIBUJO: &str = "nudo-dibujo";
pub const EVENTO_GLOBO: &str = "nudo-globo";

#[derive(Serialize, Clone)]
pub struct Objetivo {
    pub rect: RectLogico,
    pub etiqueta: Option<String>,
}

#[derive(Serialize, Clone)]
pub struct Dibujo {
    /// "vacio" | "lectura" | "senalar" | "marcar"
    pub modo: &'static str,
    pub origen: (f64, f64),
    pub objetivos: Vec<Objetivo>,
    pub generacion: u64,
}

#[derive(Serialize, Clone)]
pub struct Globo {
    pub visible: bool,
    pub texto: String,
    pub sesion: String,
    pub esperando: bool,
    pub se_ve: bool,
    /// Solo el globo de la guía: cabecera y botones propios; sin esto, el globo es el de siempre.
    pub guia: Option<GloboGuia>,
    /// Lado del globo que mira a la abejita: de ahí entra y hacia ahí sale. Lo pone `ubicar_nudo`.
    pub lado: Option<Lado>,
}

#[derive(Default)]
pub struct EstadoNudo {
    pub espera: Mutex<Option<Sender<String>>>,
    pub generacion: AtomicU64,
    ultimo: Mutex<Option<(Dibujo, Option<Globo>)>>,
    /// Ventana sobre la que se dibujó la marca: si la de adelante es otra, la marca se esconde.
    marcada: Mutex<Option<Guardada>>,
    /// La marca, la abejita y el globo están escondidos porque la ventana marcada no está al frente (la guía sigue).
    escondida: AtomicBool,
    pub uia: OnceLock<HiloUia>,
    /// Foto actual: (id, cantidad de controles).
    foto: Mutex<Option<(u64, usize)>>,
    /// Última captura de "Mostrame": las zonas se miden contra ella.
    captura: Mutex<Option<Captura>>,
    /// Último "Paso N de M" que mostró el ayudante; el seguimiento lo vuelve a poner en cada redibujo.
    paso_guia: Mutex<Option<PasoGuia>>,
    /// Lado del globo que mira al objetivo, según la última ubicación.
    pub lado_globo: Mutex<Option<Lado>>,
}

impl EstadoNudo {
    pub fn siguiente_generacion(&self) -> u64 {
        self.generacion.fetch_add(1, Ordering::SeqCst) + 1
    }
}

/// Deja lista la espera de Listo/Salir; el receptor recibe "listo" o "salir".
pub fn preparar_espera(app: &AppHandle) -> Receiver<String> {
    let (tx, rx) = channel();
    *app.state::<Estado>().nudo.espera.lock().unwrap() = Some(tx);
    rx
}

/// Un globo de guía siempre muestra el paso vigente, no el que tenía cuando se armó;
/// y todo globo, el lado de la última ubicación.
fn con_paso_guia(estado: &Estado, globo: Option<Globo>) -> Option<Globo> {
    globo.map(|mut g| {
        g.lado = *estado.nudo.lado_globo.lock().unwrap();
        if g.guia.is_some() {
            let paso = *estado.nudo.paso_guia.lock().unwrap();
            g.guia = Some(globo_guia(paso));
        }
        g
    })
}

pub fn dibujar(app: &AppHandle, dibujo: Dibujo, globo: Option<Globo>) {
    let estado = app.state::<Estado>();
    let globo = con_paso_guia(&estado, globo);
    let visible = globo.as_ref().map(|g| g.visible).unwrap_or(false);
    {
        let mut ultimo = estado.nudo.ultimo.lock().unwrap();
        recordar_marcada(&estado);
        *ultimo = Some((dibujo, globo));
    }
    mostrar_ventanas(app, visible);
}

/// Guarda la ventana en la que se está guiando, salvo que la marca esté escondida (entonces la de adelante es otra).
fn recordar_marcada(estado: &Estado) {
    if !estado.nudo.escondida.load(Ordering::SeqCst) {
        *estado.nudo.marcada.lock().unwrap() = crate::uia::ventana_guardada();
    }
}

/// Dibuja solo si nadie tomó el turno después de `generacion` (chequeo y guardado bajo el mismo lock).
pub fn dibujar_si(app: &AppHandle, generacion: u64, dibujo: Dibujo, globo: Option<Globo>) -> bool {
    let estado = app.state::<Estado>();
    let visible = globo.as_ref().map(|g| g.visible).unwrap_or(false);
    {
        let mut ultimo = estado.nudo.ultimo.lock().unwrap();
        if estado.nudo.generacion.load(Ordering::SeqCst) != generacion {
            return false;
        }
        // El interruptor guarda la config antes de `apagar` (que toma este mismo lock): mirarla acá, bajo el lock,
        // cierra la ventana entre `exige_prendido` y el dibujo. Si se apagó, `apagar` ya limpió.
        if !config_nudo(app).prendido {
            return false;
        }
        recordar_marcada(&estado);
        *ultimo = Some((dibujo, con_paso_guia(&estado, globo)));
    }
    mostrar_ventanas(app, visible);
    true
}

fn mostrar_ventanas(app: &AppHandle, globo_visible: bool) {
    emitir(app);
    // Con la ventana marcada atrás no se muestra nada: vuelve cuando ella vuelve al frente.
    if app.state::<Estado>().nudo.escondida.load(Ordering::SeqCst) {
        return;
    }
    if let Some(w) = app.get_webview_window("nudo") {
        mostrar(&w);
    }
    if let Some(g) = app.get_webview_window("nudo-globo") {
        if globo_visible {
            mostrar(&g);
        } else {
            // El globo anima su salida: se oculta después, si para entonces no volvió.
            programar_ocultar(app);
        }
    }
}

/// Oculta las ventanas del nudo una sola vez, pasada la animación de salida de las páginas,
/// salvo que en ese rato haya llegado un dibujo o un globo nuevo.
fn programar_ocultar(app: &AppHandle) {
    let app = app.clone();
    std::thread::spawn(move || {
        std::thread::sleep(Duration::from_millis(SALIDA_MS));
        let estado = app.state::<Estado>();
        // Con el lock tomado: un dibujo nuevo no puede guardarse (ni pedir `show`) entre la decisión y el `hide`.
        let ultimo = estado.nudo.ultimo.lock().unwrap();
        let hay_dibujo = ultimo.is_some();
        let globo_visible = ultimo.as_ref().and_then(|(_, g)| g.as_ref()).is_some_and(|g| g.visible);
        let ocultar = ocultar_tras_salida(hay_dibujo, globo_visible);
        for (label, si) in [("nudo", ocultar.nudo), ("nudo-globo", ocultar.globo)] {
            if let (true, Some(w)) = (si, app.get_webview_window(label)) {
                let _ = w.hide();
            }
        }
        drop(ultimo);
    });
}

/// La ventana marcada por la guía (None si no hay dibujo).
pub fn ventana_marcada(app: &AppHandle) -> Option<Guardada> {
    *app.state::<Estado>().nudo.marcada.lock().unwrap()
}

pub fn marca_escondida(app: &AppHandle) -> bool {
    app.state::<Estado>().nudo.escondida.load(Ordering::SeqCst)
}

/// Esconde o vuelve a mostrar el dibujo sin borrarlo ni terminar la guía.
pub fn aplicar_cambio(app: &AppHandle, cambio: Cambio) {
    let estado = app.state::<Estado>();
    match cambio {
        Cambio::Nada => {}
        Cambio::Esconder => {
            // Con el lock tomado: un dibujo no puede mostrar las ventanas entre la marca y el `hide`.
            let ultimo = estado.nudo.ultimo.lock().unwrap();
            if ultimo.is_none() {
                return;
            }
            estado.nudo.escondida.store(true, Ordering::SeqCst);
            for label in ["nudo", "nudo-globo"] {
                if let Some(w) = app.get_webview_window(label) {
                    let _ = w.hide();
                }
            }
            drop(ultimo);
        }
        Cambio::Mostrar => {
            let globo_visible = {
                let ultimo = estado.nudo.ultimo.lock().unwrap();
                if ultimo.is_none() || !estado.nudo.escondida.swap(false, Ordering::SeqCst) {
                    return;
                }
                ultimo.as_ref().and_then(|(_, g)| g.as_ref()).is_some_and(|g| g.visible)
            };
            mostrar_ventanas(app, globo_visible);
            ventanas::reafirmar_arriba(app);
        }
    }
}

/// Guarda el lado del globo que mira al objetivo (lo calcula `ventanas::ubicar_nudo`).
pub fn guardar_lado_globo(app: &AppHandle, lado: Lado) {
    *app.state::<Estado>().nudo.lado_globo.lock().unwrap() = Some(lado);
}

pub fn limpiar_dibujo(app: &AppHandle) {
    limpiar_si(app, None);
}

/// Con `Some(g)`, limpia solo si el turno sigue siendo `g`.
fn limpiar_si(app: &AppHandle, generacion: Option<u64>) -> bool {
    let estado = app.state::<Estado>();
    {
        let mut ultimo = estado.nudo.ultimo.lock().unwrap();
        if let Some(g) = generacion {
            if estado.nudo.generacion.load(Ordering::SeqCst) != g {
                return false;
            }
        }
        estado.nudo.siguiente_generacion();
        *ultimo = None;
        *estado.nudo.marcada.lock().unwrap() = None;
        estado.nudo.escondida.store(false, Ordering::SeqCst);
    }
    // Las páginas animan la salida (la abejita y el globo se van) y las ventanas se ocultan después.
    emitir(app);
    programar_ocultar(app);
    true
}

fn emitir(app: &AppHandle) {
    let _ = app.emit_to("nudo", EVENTO_DIBUJO, ());
    let _ = app.emit_to("nudo-globo", EVENTO_GLOBO, ());
}

fn mostrar(w: &WebviewWindow) {
    let _ = ventanas::estilo_notch(w, true);
    if !w.is_visible().unwrap_or(false) {
        let _ = w.show();
    }
    let _ = ventanas::estilo_notch(w, true);
}

fn exige_local(window: &WebviewWindow, etiquetas: &[&str]) -> Result<(), String> {
    if !etiquetas.contains(&window.label()) {
        return Err("no permitido".into());
    }
    let url = window.url().map_err(|_| "no permitido".to_string())?;
    if !es_url_local(url.as_str()) {
        return Err("no permitido".into());
    }
    Ok(())
}

fn responder(estado: &Estado, mensaje: &str) {
    if let Some(tx) = estado.nudo.espera.lock().unwrap().take() {
        let _ = tx.send(mensaje.to_string());
    }
}

/// Apagado desde la bandeja: corta la espera con "salir", suelta los avisos y saca el dibujo.
pub fn apagar(app: &AppHandle) {
    tomar_turno(app);
    limpiar_dibujo(app);
}

/// Cambió "se ve al compartir": el globo que está a la vista lo refleja.
pub fn actualizar_se_ve(app: &AppHandle, se_ve: bool) {
    let estado = app.state::<Estado>();
    if let Some((_, Some(globo))) = estado.nudo.ultimo.lock().unwrap().as_mut() {
        globo.se_ve = se_ve;
    }
    emitir(app);
}

#[tauri::command]
pub fn nudo_listo(window: WebviewWindow, estado: State<'_, Estado>) -> Result<(), String> {
    exige_local(&window, &["nudo-globo"])?;
    responder(&estado, "listo");
    Ok(())
}

#[tauri::command]
pub fn nudo_salir(
    window: WebviewWindow,
    estado: State<'_, Estado>,
    app: AppHandle,
) -> Result<(), String> {
    exige_local(&window, &["nudo-globo"])?;
    responder(&estado, "salir");
    limpiar_dibujo(&app);
    if let Some(h) = estado.nudo.uia.get() {
        h.soltar();
    }
    let _ = app.emit_to("notch", "nudo-salir", ());
    Ok(())
}

/// Botones del globo de la guía: limpia el dibujo y avisa al notch qué tocó Ando.
#[tauri::command]
pub fn nudo_guia(
    window: WebviewWindow,
    app: AppHandle,
    accion: String,
) -> Result<(), String> {
    exige_local(&window, &["nudo-globo"])?;
    let accion = AccionGuia::desde(&accion)?;
    accion_guia(&app, accion);
    Ok(())
}

/// Limpia el dibujo y avisa al notch la acción del globo. No muestra ni activa ninguna ventana.
fn accion_guia(app: &AppHandle, accion: AccionGuia) {
    tomar_turno(app);
    *app.state::<Estado>().nudo.paso_guia.lock().unwrap() = None;
    limpiar_dibujo(app);
    let _ = app.emit_to("notch", accion.evento(), ());
}

/// Atajo de la guía: con un globo de guía a la vista hace lo mismo que su botón y devuelve `true`;
/// si no, devuelve `false` y el atajo abre la cajita.
pub fn atajo_guia_en_curso(app: &AppHandle) -> bool {
    let estado = app.state::<Estado>();
    let decision = {
        let ultimo = estado.nudo.ultimo.lock().unwrap();
        let globo = ultimo.as_ref().and_then(|(_, g)| g.as_ref()).filter(|g| g.visible).and_then(|g| g.guia.as_ref());
        atajo_guia(globo)
    };
    match decision {
        AtajoGuia::Avanzar(accion) => {
            accion_guia(app, accion);
            true
        }
        AtajoGuia::AbrirCajita => false,
    }
}

#[derive(Serialize)]
pub struct EstadoPagina {
    pub dibujo: Option<Dibujo>,
    pub globo: Option<Globo>,
}

/// Estado actual para la página que lo pide (al cargar y tras cada aviso).
#[tauri::command]
pub fn nudo_pagina_estado(window: WebviewWindow, estado: State<'_, Estado>) -> Result<EstadoPagina, String> {
    exige_local(&window, &["nudo", "nudo-globo"])?;
    let ultimo = estado.nudo.ultimo.lock().unwrap().clone();
    let (dibujo, globo) = match ultimo {
        Some((d, g)) => (Some(d), g),
        None => (None, None),
    };
    Ok(if window.label() == "nudo" {
        EstadoPagina { dibujo, globo: None }
    } else {
        EstadoPagina { dibujo: None, globo }
    })
}

/// Diagnóstico (COLMENA_NUDO_DIAG=1): señala un rectángulo en el centro del monitor del notch.
pub fn dibujo_de_prueba(app: AppHandle) {
    std::thread::spawn(move || {
        let resultado = prueba(&app).unwrap_or_else(|e| format!("error: {e}"));
        limpiar_dibujo(&app);
        if let Ok(dir) = app.path().app_config_dir() {
            let _ = std::fs::write(dir.join("nudo-diagnostico.txt"), format!("{resultado}\n"));
        }
    });
}

fn prueba(app: &AppHandle) -> Result<String, String> {
    let monitor = ventanas::monitor_notch(app)?;
    let escala = monitor.scale_factor();
    let ancho = f64::from(monitor.size().width) / escala;
    let alto = f64::from(monitor.size().height) / escala;
    let rect = RectLogico { x: ancho / 2.0 - 100.0, y: alto / 2.0 - 20.0, ancho: 200.0, alto: 40.0 };
    let espera = preparar_espera(app);
    ventanas::ubicar_nudo(app, &monitor, Some(&rect))?;
    let estado = app.state::<Estado>();
    let dibujo = Dibujo {
        modo: "senalar",
        origen: colmena_nucleo::nudo::coords::origen_nudo((ancho, alto)),
        objetivos: vec![Objetivo { rect, etiqueta: None }],
        generacion: estado.nudo.siguiente_generacion(),
    };
    let globo = Globo {
        visible: true,
        texto: "Prueba del nudo".into(),
        sesion: "Colmena".into(),
        esperando: true,
        se_ve: false,
        guia: None,
        lado: None,
    };
    dibujar(app, dibujo, Some(globo));
    espera
        .recv_timeout(Duration::from_secs(120))
        .map_err(|_| "sin respuesta en 120 s".to_string())
}

// ---- Comandos remotos (página del notch) ----

#[derive(Serialize)]
pub struct VentanaInfo {
    pub titulo: String,
    pub proceso: String,
}

#[derive(Serialize)]
pub struct ListaControles {
    pub foto: u64,
    pub ventana: VentanaInfo,
    /// "<x>,<y> <ancho>x<alto>" en píxeles físicos.
    pub monitor: String,
    pub controles: Vec<ControlListado>,
}

#[derive(Serialize)]
pub struct Mostrar {
    pub foto: u64,
    pub ventana: VentanaInfo,
    pub controles: Vec<ControlListado>,
    pub imagen: ImagenCodificada,
}

#[derive(Serialize)]
pub struct EstadoPc {
    pub prendido: bool,
    pub se_ve_al_compartir: bool,
}

const SEGUIMIENTO: Duration = Duration::from_millis(250);
const FIN_DESTELLO: Duration = Duration::from_millis(500);

/// Reloj monótono en ms para el vencimiento de la captura.
fn ahora_ms() -> u64 {
    static INICIO: OnceLock<Instant> = OnceLock::new();
    INICIO.get_or_init(Instant::now).elapsed().as_millis() as u64
}

fn config_nudo(app: &AppHandle) -> ConfigNudo {
    crate::leer_config_archivo(&app.state::<Estado>().ruta_config).nudo
}

fn exige_prendido(app: &AppHandle) -> Result<(), String> {
    if !config_nudo(app).prendido {
        return Err(ERR_APAGADO.into());
    }
    Ok(())
}

fn exige_nudo(window: &WebviewWindow, estado: &Estado, app: &AppHandle) -> Result<(), String> {
    exige_ventana(window, estado, "notch")?;
    exige_prendido(app)?;
    // Si las ventanas no se pudieron crear al arrancar, no se finge que se dibujó.
    if app.get_webview_window("nudo").is_none()
        || app.get_webview_window("nudo-globo").is_none()
        || estado.nudo.uia.get().is_none()
    {
        return Err(ERR_FALLO_PC.into());
    }
    Ok(())
}

async fn en_hilo<T: Send + 'static>(
    f: impl FnOnce() -> Result<T, String> + Send + 'static,
) -> Result<T, String> {
    tauri::async_runtime::spawn_blocking(f)
        .await
        .map_err(|_| ERR_FALLO_PC.to_string())?
        .map_err(|e| codigo_de_error(&e))
}

fn hilo(app: &AppHandle) -> Result<&HiloUia, String> {
    app.state::<Estado>()
        .inner()
        .nudo
        .uia
        .get()
        .ok_or_else(|| ERR_FALLO_PC.to_string())
}

/// Nuevo dibujo: corta la espera anterior ("salir"), suelta los avisos y frena el seguimiento.
fn tomar_turno(app: &AppHandle) -> u64 {
    let estado = app.state::<Estado>();
    let generacion = {
        let _ultimo = estado.nudo.ultimo.lock().unwrap();
        estado.nudo.siguiente_generacion()
    };
    responder(&estado, "salir");
    if let Some(h) = estado.nudo.uia.get() {
        h.soltar();
    }
    generacion
}

fn rect_monitor(m: &Monitor) -> Rect {
    let p = m.position();
    let s = m.size();
    Rect { x: p.x, y: p.y, ancho: s.width, alto: s.height }
}

fn tam_logico(m: &Monitor) -> (f64, f64) {
    let e = m.scale_factor();
    (f64::from(m.size().width) / e, f64::from(m.size().height) / e)
}

fn monitor_de_rect(app: &AppHandle, r: Rect) -> Option<Monitor> {
    let monitores = app.available_monitors().ok()?;
    let rects: Vec<Rect> = monitores.iter().map(rect_monitor).collect();
    monitor_para(r, &rects).map(|i| monitores[i].clone())
}

fn en_overlay(app: &AppHandle, fisico: Rect) -> Option<(Monitor, RectLogico)> {
    let m = monitor_de_rect(app, fisico)?;
    let l = a_overlay(fisico, rect_monitor(&m), m.scale_factor())?;
    Some((m, l))
}

fn destello(app: &AppHandle, generacion: u64, ventana: Option<Rect>) {
    let monitor = ventana
        .and_then(|r| monitor_de_rect(app, r))
        .or_else(|| ventanas::monitor_notch(app).ok());
    let Some(m) = monitor else { return };
    let _ = ventanas::ubicar_nudo(app, &m, None);
    let dibujo = Dibujo {
        modo: "lectura",
        origen: origen_nudo(tam_logico(&m)),
        objetivos: Vec::new(),
        generacion,
    };
    dibujar_si(app, generacion, dibujo, None);
}

fn controles(app: &AppHandle) -> Result<ListaControles, String> {
    let hilo = hilo(app)?;
    let generacion = tomar_turno(app);
    destello(app, generacion, hilo.rect_ventana());
    let lectura = hilo.leer();
    let para_limpiar = app.clone();
    std::thread::spawn(move || {
        std::thread::sleep(FIN_DESTELLO);
        limpiar_si(&para_limpiar, Some(generacion));
    });
    let l = lectura?;
    exige_prendido(app)?;
    *app.state::<Estado>().nudo.foto.lock().unwrap() = Some((l.foto, l.controles.len()));
    let monitor = monitor_de_rect(app, l.ventana).map(|m| rect_monitor(&m)).unwrap_or(l.ventana);
    Ok(ListaControles {
        foto: l.foto,
        ventana: VentanaInfo { titulo: limpiar_nombre(&l.titulo), proceso: limpiar_nombre(&l.proceso) },
        monitor: texto_monitor(monitor),
        controles: l.controles,
    })
}

/// Captura la ventana al frente (antes del destello, así no sale en la imagen) y lee sus controles.
fn mostrame(app: &AppHandle) -> Result<Mostrar, String> {
    let hilo = hilo(app)?;
    let (ventana_id, visible) = hilo.ventana_visible().ok_or_else(|| ERR_SIN_VENTANA.to_string())?;
    let monitor = monitor_de_rect(app, visible).ok_or_else(|| ERR_SIN_VENTANA.to_string())?;
    let recorte = recorte_captura(visible, rect_monitor(&monitor)).ok_or_else(|| ERR_SIN_VENTANA.to_string())?;
    let (ancho, alto) = tam_imagen(recorte, LADO_MAX_IMAGEN);
    let bgra = capturar_bgra(recorte, ancho, alto)?;
    let imagen = codificar(&bgra, ancho, alto, TOPE_IMAGEN)?;
    drop(bgra);

    let generacion = tomar_turno(app);
    destello(app, generacion, Some(visible));
    let lectura = hilo.leer_para_mostrar();
    let para_limpiar = app.clone();
    std::thread::spawn(move || {
        std::thread::sleep(FIN_DESTELLO);
        limpiar_si(&para_limpiar, Some(generacion));
    });
    let l = lectura?;
    // Si la ventana al frente cambió mientras se leía, la imagen y los controles serían de ventanas distintas.
    if !misma_ventana((ventana_id, visible), hilo.ventana_visible()) {
        return Err(ERR_SIN_VENTANA.into());
    }
    exige_prendido(app)?;
    let estado = app.state::<Estado>();
    *estado.nudo.foto.lock().unwrap() = Some((l.foto, l.controles.len()));
    *estado.nudo.captura.lock().unwrap() = Some(Captura {
        foto: l.foto,
        ventana_id,
        ventana: visible,
        recorte,
        ancho,
        alto,
        creada_ms: ahora_ms(),
    });
    Ok(Mostrar {
        foto: l.foto,
        ventana: VentanaInfo { titulo: limpiar_nombre(&l.titulo), proceso: limpiar_nombre(&l.proceso) },
        controles: l.controles,
        imagen,
    })
}

/// Captura vigente para `foto`: misma foto, menos de 5 minutos y la ventana sin moverse ni cambiar.
fn captura_para(app: &AppHandle, hilo: &HiloUia, foto: u64) -> Result<Captura, String> {
    let guardada = *app.state::<Estado>().nudo.captura.lock().unwrap();
    captura_vigente(guardada.as_ref(), foto, hilo.ventana_visible(), ahora_ms())
}

fn senalar_zona(app: &AppHandle, foto: u64, zona: ZonaImagen, texto: String, sesion: String, guia: bool) -> Result<String, String> {
    let hilo = hilo(app)?;
    let cap = captura_para(app, hilo, foto)?;
    validar_zona(&zona, &cap)?;
    let fisico = zona_a_fisico(&zona, &cap);
    let (monitor, logico) = en_overlay(app, fisico).ok_or_else(|| ERR_FOTO_VIEJA.to_string())?;
    dibujar_senal(app, &monitor, logico, texto, sesion, false, guia)?;
    Ok("ok".into())
}

fn marcar_zonas(app: &AppHandle, foto: u64, zonas: Vec<ZonaEtiquetada>, sesion: String, guia: bool) -> Result<String, String> {
    let hilo = hilo(app)?;
    let cap = captura_para(app, hilo, foto)?;
    let zonas = validar_zonas(zonas, &cap)?;
    let fisicos = zonas.into_iter().map(|z| (zona_a_fisico(&z.zona(), &cap), z.etiqueta)).collect();
    dibujar_marcas(app, fisicos, sesion, guia)
}

/// Re-lee la posición cada 250 ms mientras el turno sea `generacion`; si el control se va, queda el globo sin línea.
fn seguir_objetivo(app: AppHandle, generacion: u64, foto: u64, idx: usize, inicial: Rect, origen: (f64, f64), globo: Globo) {
    std::thread::spawn(move || {
        let mut previo = Some(inicial);
        let mut menus_previos = crate::uia::rects_efimeros();
        let mut origen = origen;
        loop {
            std::thread::sleep(SEGUIMIENTO);
            let estado = app.state::<Estado>();
            if estado.nudo.generacion.load(Ordering::SeqCst) != generacion {
                return;
            }
            let Some(h) = estado.nudo.uia.get() else { return };
            let actual = h.seguir(foto, idx).ok();
            // Un menú abierto después de mostrar el paso puede caer sobre el globo: también reubica.
            let menus = crate::uia::rects_efimeros();
            if actual == previo && menus == menus_previos {
                continue;
            }
            // Respaldo de "usado" para un botón que abre un menú sin avisar por UIA: el menú nuevo quedó pegado a él.
            if actual.is_some_and(|r| popup_nuevo_pegado(r, &menus_previos, &menus)) {
                responder(&estado, "usado");
            }
            previo = actual;
            menus_previos = menus;
            let ubicado = actual.and_then(|r| en_overlay(&app, r));
            let objetivos = match &ubicado {
                Some((m, l)) => {
                    if estado.nudo.generacion.load(Ordering::SeqCst) != generacion {
                        return;
                    }
                    let _ = ventanas::ubicar_nudo(&app, m, Some(l));
                    origen = origen_nudo(tam_logico(m));
                    vec![Objetivo { rect: *l, etiqueta: None }]
                }
                None => Vec::new(),
            };
            let dibujo = Dibujo { modo: "senalar", origen, objetivos, generacion };
            if !dibujar_si(&app, generacion, dibujo, Some(globo.clone())) {
                return;
            }
        }
    });
}

fn esperar_resultado(app: &AppHandle, generacion: u64, rx: Receiver<String>, segundos: u32) -> String {
    let r = match rx.recv_timeout(Duration::from_secs(u64::from(segundos))) {
        Ok(m) => m,
        Err(RecvTimeoutError::Timeout) => "vencido".into(),
        Err(RecvTimeoutError::Disconnected) => "salir".into(),
    };
    // Si otro pedido ya tomó el turno, el dibujo y los avisos son suyos: no se tocan.
    if limpiar_si(app, Some(generacion)) {
        let estado = app.state::<Estado>();
        estado.nudo.espera.lock().unwrap().take();
        if let Some(h) = estado.nudo.uia.get() {
            h.soltar();
        }
    }
    r
}

fn senalar(
    app: &AppHandle,
    foto: u64,
    n: u32,
    texto: String,
    sesion: String,
    esperar: Option<u32>,
    guia: bool,
) -> Result<String, String> {
    let hilo = hilo(app)?;
    let actual = *app.state::<Estado>().nudo.foto.lock().unwrap();
    let idx = indice_en_foto(actual, foto, n)?;
    let fisico = hilo.rect(foto, idx)?;
    let (monitor, logico) = en_overlay(app, fisico).ok_or_else(|| ERR_FOTO_VIEJA.to_string())?;
    let (senal, rx) = dibujar_senal(app, &monitor, logico, texto, sesion, esperar.is_some(), guia)?;
    if !senal.dibujado {
        return Ok(if esperar.is_some() { "salir" } else { "ok" }.into());
    }
    let generacion = senal.generacion;
    seguir_objetivo(app.clone(), generacion, foto, idx, fisico, senal.origen, senal.globo);

    let (Some(rx), Some(segundos)) = (rx, esperar) else {
        return Ok("ok".into());
    };
    if let Some(tx) = app.state::<Estado>().nudo.espera.lock().unwrap().clone() {
        hilo.vigilar(foto, idx, tx);
    }
    Ok(esperar_resultado(app, generacion, rx, segundos))
}

fn marcar(app: &AppHandle, foto: u64, marcas: Vec<Marca>, sesion: String, guia: bool) -> Result<String, String> {
    let hilo = hilo(app)?;
    let actual = *app.state::<Estado>().nudo.foto.lock().unwrap();
    let mut fisicos = Vec::with_capacity(marcas.len());
    for m in marcas {
        let idx = indice_en_foto(actual, foto, m.n)?;
        fisicos.push((hilo.rect(foto, idx)?, m.etiqueta));
    }
    dibujar_marcas(app, fisicos, sesion, guia)
}

struct Senal {
    generacion: u64,
    origen: (f64, f64),
    globo: Globo,
    dibujado: bool,
}

/// Toma el turno y dibuja una señal con globo; con `esperar`, deja lista la espera de Listo/Salir.
fn dibujar_senal(
    app: &AppHandle,
    monitor: &Monitor,
    logico: RectLogico,
    texto: String,
    sesion: String,
    esperar: bool,
    guia: bool,
) -> Result<(Senal, Option<Receiver<String>>), String> {
    exige_prendido(app)?;
    let se_ve = config_nudo(app).se_ve_al_compartir;

    let generacion = tomar_turno(app);
    if guia {
        *app.state::<Estado>().nudo.paso_guia.lock().unwrap() = None;
    }
    let rx = esperar.then(|| preparar_espera(app));
    ventanas::ubicar_nudo(app, monitor, Some(&logico))?;
    let origen = origen_nudo(tam_logico(monitor));
    let globo = Globo {
        visible: true,
        texto,
        sesion,
        esperando: esperar,
        se_ve,
        guia: guia.then(|| globo_guia(None)),
        lado: None,
    };
    let dibujo = Dibujo {
        modo: "senalar",
        origen,
        objetivos: vec![Objetivo { rect: logico, etiqueta: None }],
        generacion,
    };
    let dibujado = dibujar_si(app, generacion, dibujo, Some(globo.clone()));
    if !dibujado {
        exige_prendido(app)?;
    }
    Ok((Senal { generacion, origen, globo, dibujado }, rx))
}

/// Toma el turno y dibuja las marcas en el monitor de la primera.
fn dibujar_marcas(app: &AppHandle, fisicos: Vec<(Rect, String)>, sesion: String, guia: bool) -> Result<String, String> {
    let primero_fisico = fisicos.first().map(|f| f.0).ok_or_else(|| ERR_FOTO_VIEJA.to_string())?;
    let monitor = monitor_de_rect(app, primero_fisico).ok_or_else(|| ERR_FOTO_VIEJA.to_string())?;
    let (mr, escala) = (rect_monitor(&monitor), monitor.scale_factor());
    // Las marcas que caen en otro monitor no se dibujan: el overlay cubre uno solo.
    let objetivos: Vec<Objetivo> = fisicos
        .into_iter()
        .filter_map(|(r, etiqueta)| a_overlay(r, mr, escala).map(|rect| Objetivo { rect, etiqueta: Some(etiqueta) }))
        .collect();
    let Some(primero) = objetivos.first().map(|o| o.rect) else {
        return Err(ERR_FOTO_VIEJA.into());
    };
    exige_prendido(app)?;
    let se_ve = config_nudo(app).se_ve_al_compartir;

    let generacion = tomar_turno(app);
    if guia {
        *app.state::<Estado>().nudo.paso_guia.lock().unwrap() = None;
    }
    ventanas::ubicar_nudo(app, &monitor, Some(&primero))?;
    let globo = Globo {
        visible: true,
        texto: texto_marcas(objetivos.len()),
        sesion,
        esperando: false,
        se_ve,
        guia: guia.then(|| globo_guia(None)),
        lado: None,
    };
    let dibujo = Dibujo { modo: "marcar", origen: origen_nudo(tam_logico(&monitor)), objetivos, generacion };
    if !dibujar_si(app, generacion, dibujo, Some(globo)) {
        exige_prendido(app)?;
    }
    Ok("ok".into())
}

#[tauri::command]
pub async fn nudo_controles(
    window: WebviewWindow,
    estado: State<'_, Estado>,
    app: AppHandle,
) -> Result<ListaControles, String> {
    exige_nudo(&window, &estado, &app)?;
    en_hilo(move || controles(&app)).await
}

#[allow(clippy::too_many_arguments)]
#[tauri::command]
pub async fn nudo_senalar(
    window: WebviewWindow,
    estado: State<'_, Estado>,
    app: AppHandle,
    foto: u64,
    n: u32,
    texto: String,
    sesion: String,
    esperar: Option<u32>,
    guia: Option<bool>,
) -> Result<String, String> {
    exige_nudo(&window, &estado, &app)?;
    let texto = validar_texto(&texto, TEXTO_MAX)?;
    let sesion = validar_texto(&sesion, SESION_MAX)?;
    let esperar = validar_espera(esperar)?;
    let guia = guia.unwrap_or(false);
    en_hilo(move || senalar(&app, foto, n, texto, sesion, esperar, guia)).await
}

#[tauri::command]
pub async fn nudo_marcar(
    window: WebviewWindow,
    estado: State<'_, Estado>,
    app: AppHandle,
    foto: u64,
    marcas: Vec<Marca>,
    sesion: String,
    guia: Option<bool>,
) -> Result<String, String> {
    exige_nudo(&window, &estado, &app)?;
    let marcas = validar_marcas(marcas)?;
    let guia = guia.unwrap_or(false);
    let sesion = validar_texto(&sesion, SESION_MAX)?;
    en_hilo(move || marcar(&app, foto, marcas, sesion, guia)).await
}

#[tauri::command]
pub async fn nudo_mostrar(
    window: WebviewWindow,
    estado: State<'_, Estado>,
    app: AppHandle,
) -> Result<Mostrar, String> {
    exige_nudo(&window, &estado, &app)?;
    en_hilo(move || mostrame(&app)).await
}

#[tauri::command]
pub async fn nudo_senalar_zona(
    window: WebviewWindow,
    estado: State<'_, Estado>,
    app: AppHandle,
    foto: u64,
    zona: ZonaImagen,
    texto: String,
    sesion: String,
    guia: Option<bool>,
) -> Result<String, String> {
    exige_nudo(&window, &estado, &app)?;
    let texto = validar_texto(&texto, TEXTO_MAX)?;
    let sesion = validar_texto(&sesion, SESION_MAX)?;
    let guia = guia.unwrap_or(false);
    en_hilo(move || senalar_zona(&app, foto, zona, texto, sesion, guia)).await
}

#[tauri::command]
pub async fn nudo_marcar_zonas(
    window: WebviewWindow,
    estado: State<'_, Estado>,
    app: AppHandle,
    foto: u64,
    zonas: Vec<ZonaEtiquetada>,
    sesion: String,
    guia: Option<bool>,
) -> Result<String, String> {
    exige_nudo(&window, &estado, &app)?;
    let sesion = validar_texto(&sesion, SESION_MAX)?;
    let guia = guia.unwrap_or(false);
    en_hilo(move || marcar_zonas(&app, foto, zonas, sesion, guia)).await
}

#[tauri::command]
pub async fn nudo_limpiar(
    window: WebviewWindow,
    estado: State<'_, Estado>,
    app: AppHandle,
) -> Result<String, String> {
    exige_ventana(&window, &estado, "notch")?;
    en_hilo(move || {
        tomar_turno(&app);
        limpiar_dibujo(&app);
        Ok("ok".to_string())
    })
    .await
}

/// Solo lectura; responde también con el nudo apagado.
#[tauri::command]
pub async fn nudo_estado(window: WebviewWindow, estado: State<'_, Estado>) -> Result<EstadoPc, String> {
    exige_ventana(&window, &estado, "notch")?;
    let c = crate::leer_config_archivo(&estado.ruta_config).nudo;
    Ok(EstadoPc { prendido: c.prendido, se_ve_al_compartir: c.se_ve_al_compartir })
}

/// Interruptor "se ve al compartir" del globo; solo lo puede llamar la ventana `nudo-globo`.
#[tauri::command(rename_all = "snake_case")]
pub fn nudo_visibilidad(
    window: WebviewWindow,
    app: AppHandle,
    estado: State<'_, Estado>,
    se_ve: bool,
) -> Result<(), String> {
    exige_local(&window, &["nudo-globo"])?;
    let mut nudo = crate::leer_config_archivo(&estado.ruta_config).nudo;
    let antes = nudo.se_ve_al_compartir;
    let resultado = cambiar_visibilidad(&app, &estado, &mut nudo, se_ve);
    if resultado.is_err() {
        let _ = ventanas::aplicar_visibilidad(&app, antes, crate::reunion::escuchando(&app));
    }
    actualizar_se_ve(&app, if resultado.is_ok() { se_ve } else { antes });
    crate::bandeja::sincronizar_nudo(&app);
    resultado
}

/// Aplica la afinidad primero y guarda solo si salió bien: la config nunca dice "no se ve" sin que sea cierto.
pub fn cambiar_visibilidad(
    app: &AppHandle,
    estado: &Estado,
    nudo: &mut ConfigNudo,
    se_ve: bool,
) -> Result<(), String> {
    ventanas::aplicar_visibilidad(app, se_ve, estado.reunion.escuchando.load(std::sync::atomic::Ordering::SeqCst))?;
    nudo.se_ve_al_compartir = se_ve;
    crate::bandeja::guardar_nudo(estado, *nudo)
}

/// El notch avisa el "Paso N de M" que mostró el ayudante; si el globo a la vista es de guía, lo actualiza.
#[tauri::command]
pub async fn nudo_guia_paso(
    window: WebviewWindow,
    estado: State<'_, Estado>,
    app: AppHandle,
    paso: u32,
    total: u32,
    fin: bool,
) -> Result<String, String> {
    exige_ventana(&window, &estado, "notch")?;
    let p = acotar_paso(paso, total, fin);
    *estado.nudo.paso_guia.lock().unwrap() = Some(p);
    {
        let mut ultimo = estado.nudo.ultimo.lock().unwrap();
        if let Some((_, Some(globo))) = ultimo.as_mut() {
            if globo.guia.is_some() {
                globo.guia = Some(globo_guia(Some(p)));
            }
        }
    }
    emitir(&app);
    Ok("ok".into())
}
