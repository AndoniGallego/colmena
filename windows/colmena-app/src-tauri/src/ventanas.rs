use colmena_nucleo::config::leer_config;
use colmena_nucleo::forma::RegionFisica;
use colmena_nucleo::foco::{pasos_foco, PasoFoco};
use colmena_nucleo::nudo::coords::{a_overlay, lado_hacia, origen_nudo, posicion_globo_evitando, RectLogico};
use colmena_nucleo::posicion::{ancla_de, encajar, monitor_de, Rect};
use colmena_nucleo::reunion::ventana::{recordada, VentanaGuardada, ALTO_MIN, ANCHO_MIN, TAMANO_INICIAL};
use colmena_nucleo::validar::{url_colmena, url_notch, url_reunion, x_centrada};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::Duration;

use tauri::{AppHandle, Manager, Monitor, WebviewUrl, WebviewWindow, WebviewWindowBuilder, WindowEvent};

#[cfg(not(windows))]
use tauri::{LogicalSize, PhysicalPosition};
use url::Url;

use crate::{programar_guardado_ancla, Estado};

pub const ARGS: &str = "--autoplay-policy=no-user-gesture-required";
const SEPARACION_ARRIBA: f64 = 5.0;

pub(crate) fn estilo_notch(window: &WebviewWindow, no_activar: bool) -> Result<(), String> {
    estilo_notch_impl(window, no_activar)
}

#[cfg(windows)]
fn estilo_notch_impl(window: &WebviewWindow, no_activar: bool) -> Result<(), String> {
    use windows_sys::Win32::UI::WindowsAndMessaging::{
        GetWindowLongPtrW, SetWindowLongPtrW, GWL_EXSTYLE, WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW,
    };

    let hwnd = window.hwnd().map_err(|e| e.to_string())?.0;
    unsafe {
        let mut ex = GetWindowLongPtrW(hwnd, GWL_EXSTYLE);
        ex |= WS_EX_TOOLWINDOW as isize;
        if no_activar {
            ex |= WS_EX_NOACTIVATE as isize;
        } else {
            ex &= !(WS_EX_NOACTIVATE as isize);
        }
        SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex);
    }
    Ok(())
}

#[cfg(not(windows))]
fn estilo_notch_impl(_window: &WebviewWindow, _no_activar: bool) -> Result<(), String> {
    Ok(())
}

fn cfg_desde_app(app: &AppHandle) -> colmena_nucleo::config::Config {
    let estado = app.state::<Estado>();
    std::fs::read_to_string(&estado.ruta_config)
        .map(|t| leer_config(&t))
        .unwrap_or_default()
}

fn monitor_rect(m: &Monitor) -> Rect {
    let p = m.position();
    let s = m.size();
    Rect {
        x: p.x,
        y: p.y,
        ancho: s.width,
        alto: s.height,
    }
}

pub(crate) fn monitors_iguales(a: &Monitor, b: &Monitor) -> bool {
    a.name() == b.name()
        && a.position().x == b.position().x
        && a.position().y == b.position().y
        && a.size().width == b.size().width
        && a.size().height == b.size().height
}

pub fn monitor_notch(app: &AppHandle) -> Result<Monitor, String> {
    let monitors = app
        .available_monitors()
        .map_err(|e| e.to_string())?;
    if monitors.is_empty() {
        return Err("sin monitor".into());
    }

    let cfg = cfg_desde_app(app);
    if let Some(ref wanted) = cfg.monitor {
        if let Some(m) = monitors
            .iter()
            .find(|m| m.name().map(|n| n == wanted).unwrap_or(false))
        {
            return Ok(m.clone());
        }
    }

    if let Ok(Some(primary)) = app.primary_monitor() {
        if let Some(m) = monitors.iter().find(|m| monitors_iguales(m, &primary)) {
            return Ok(m.clone());
        }
    }

    Ok(monitors[0].clone())
}

fn posicion_notch(
    app: &AppHandle,
    ancho_logico: u32,
    alto_logico: u32,
) -> Result<(i32, i32, u32, u32), String> {
    let monitors = app
        .available_monitors()
        .map_err(|e| e.to_string())?;
    let rects: Vec<Rect> = monitors.iter().map(monitor_rect).collect();

    let estado = app.state::<Estado>();
    let ancla_guardada = *estado.ancla.lock().unwrap();

    if let Some(ancla) = ancla_guardada {
        if let Some(idx) = monitor_de(ancla, &rects) {
            let monitor = &monitors[idx];
            let scale = monitor.scale_factor();
            let ancho_fisico = (f64::from(ancho_logico) * scale).round() as u32;
            let alto_fisico = (f64::from(alto_logico) * scale).round() as u32;
            let (x, y) = encajar(ancla, ancho_fisico, alto_fisico, rects[idx]);
            return Ok((x, y, ancho_fisico, alto_fisico));
        }
    }

    let monitor = monitor_notch(app)?;
    let pos = monitor.position();
    let size = monitor.size();
    let scale = monitor.scale_factor();
    let ancho_fisico = (f64::from(ancho_logico) * scale).round() as u32;
    let alto_fisico = (f64::from(alto_logico) * scale).round() as u32;
    let x = x_centrada(pos.x, size.width, ancho_fisico);
    let y = pos.y + (SEPARACION_ARRIBA * scale).round() as i32;
    Ok((x, y, ancho_fisico, alto_fisico))
}

pub fn ubicar_notch(
    app: &AppHandle,
    window: &WebviewWindow,
    ancho_logico: u32,
    alto_logico: u32,
) -> Result<(), String> {
    let (x, y, ancho_fisico, alto_fisico) = posicion_notch(app, ancho_logico, alto_logico)?;

    {
        let estado = app.state::<Estado>();
        *estado.ultima_pos.lock().unwrap() = Some((x, y));
    }

    #[cfg(windows)]
    {
        use windows_sys::Win32::UI::WindowsAndMessaging::{SetWindowPos, SWP_NOACTIVATE, SWP_NOZORDER};

        let hwnd = window.hwnd().map_err(|e| e.to_string())?.0;
        unsafe {
            SetWindowPos(
                hwnd,
                std::ptr::null_mut(),
                x,
                y,
                ancho_fisico as i32,
                alto_fisico as i32,
                SWP_NOZORDER | SWP_NOACTIVATE,
            );
        }
        Ok(())
    }

    #[cfg(not(windows))]
    {
        window
            .set_size(LogicalSize::new(ancho_logico, alto_logico))
            .map_err(|e| e.to_string())?;
        window
            .set_position(PhysicalPosition::new(x, y))
            .map_err(|e| e.to_string())
    }
}

fn registrar_movimiento_notch(app: &AppHandle, window: &WebviewWindow) {
    let app_cl = app.clone();
    let window_cl = window.clone();
    window.on_window_event(move |event| {
        if let WindowEvent::Moved(pos) = event {
            let estado = app_cl.state::<Estado>();
            let ultima = *estado.ultima_pos.lock().unwrap();
            if ultima == Some((pos.x, pos.y)) {
                return;
            }
            let Ok(fisico) = window_cl.inner_size() else {
                return;
            };
            let nueva = ancla_de(pos.x, pos.y, fisico.width);
            *estado.ancla.lock().unwrap() = Some(nueva);
            programar_guardado_ancla(&estado, Some(nueva));
        }
    });
}

pub fn reposicionar_notch_actual(app: &AppHandle) -> Result<(), String> {
    let Some(window) = app.get_webview_window("notch") else {
        return Ok(());
    };
    let scale = window.scale_factor().map_err(|e| e.to_string())?;
    let fisico = window.inner_size().map_err(|e| e.to_string())?;
    let ancho = (f64::from(fisico.width) / scale).round() as u32;
    let alto = (f64::from(fisico.height) / scale).round() as u32;
    ubicar_notch(app, &window, ancho, alto)
}

pub fn crear_origen(app: &AppHandle) -> Result<WebviewWindow, String> {
    if let Some(w) = app.get_webview_window("origen") {
        w.show().map_err(|e| e.to_string())?;
        w.set_focus().map_err(|e| e.to_string())?;
        return Ok(w);
    }
    WebviewWindowBuilder::new(app, "origen", WebviewUrl::App("origen.html".into()))
        .title("Colmena")
        .inner_size(420.0, 260.0)
        .resizable(false)
        .additional_browser_args(ARGS)
        .build()
        .map_err(|e| e.to_string())
}

pub fn crear_notebook(app: &AppHandle) -> Result<WebviewWindow, String> {
    if let Some(w) = app.get_webview_window("notebook") {
        w.show().map_err(|e| e.to_string())?;
        w.set_focus().map_err(|e| e.to_string())?;
        return Ok(w);
    }
    WebviewWindowBuilder::new(app, "notebook", WebviewUrl::App("notebook.html".into()))
        .title("Dirección de la notebook")
        .inner_size(420.0, 300.0)
        .resizable(false)
        .additional_browser_args(ARGS)
        .build()
        .map_err(|e| e.to_string())
}

pub fn crear_atajos(app: &AppHandle) -> Result<WebviewWindow, String> {
    if let Some(w) = app.get_webview_window("atajos") {
        w.show().map_err(|e| e.to_string())?;
        w.set_focus().map_err(|e| e.to_string())?;
        return Ok(w);
    }
    let window = WebviewWindowBuilder::new(app, "atajos", WebviewUrl::App("atajos.html".into()))
        .title("Atajos")
        .inner_size(460.0, 340.0)
        .center()
        .resizable(false)
        .additional_browser_args(ARGS)
        .build()
        .map_err(|e| e.to_string())?;
    // Si la ventana se cierra a mitad de una grabación, los atajos vuelven igual.
    let app_cl = app.clone();
    window.on_window_event(move |event| {
        if let WindowEvent::Destroyed = event {
            crate::atajos::reanudar(&app_cl);
        }
    });
    Ok(window)
}

/// Muestra el notch si está oculto y lo oculta si está visible.
pub fn alternar_notch(app: &AppHandle) {
    if let Some(w) = app.get_webview_window("notch") {
        if w.is_visible().unwrap_or(false) {
            let _ = w.hide();
        } else {
            let _ = w.show();
            let _ = estilo_notch(&w, true);
        }
    }
}

/// Trae la ventana grande al frente sin recargarla; si no existe, la abre.
pub fn traer_colmena(app: &AppHandle) {
    if let Some(w) = app.get_webview_window("colmena") {
        let _ = w.show();
        let _ = w.unminimize();
        let _ = w.set_focus();
        return;
    }
    let origen = app.state::<Estado>().origen.lock().unwrap().clone();
    if let Some(o) = origen {
        let _ = abrir_colmena_ventana(app, &o, None);
    }
}

pub fn crear_notch(app: &AppHandle, origen: &str) -> Result<WebviewWindow, String> {
    let url = url_notch(origen);
    let window = WebviewWindowBuilder::new(
        app,
        "notch",
        WebviewUrl::External(url.parse().map_err(|_| "url inválida")?),
    )
    .decorations(false)
    .transparent(true)
    .always_on_top(true)
    .skip_taskbar(true)
    .focused(false)
    .resizable(false)
    .shadow(false)
    .inner_size(240.0, 64.0)
    .additional_browser_args(ARGS)
    .build()
    .map_err(|e| e.to_string())?;

    estilo_notch(&window, true)?;
    registrar_movimiento_notch(app, &window);
    ubicar_notch(app, &window, 240, 64)?;
    Ok(window)
}

const ETIQUETA_REUNION: &str = "reunion";

/// Ventana "Reunión": se abre al empezar a escuchar y sigue la reunión con marco normal.
/// Si ya existe la trae al frente; solo se abre con una reunión en curso.
pub fn mostrar_reunion(app: &AppHandle) -> Result<(), String> {
    if !crate::reunion::escuchando(app) {
        return Ok(());
    }
    if let Some(w) = app.get_webview_window(ETIQUETA_REUNION) {
        let _ = w.show();
        let _ = w.unminimize();
        return w.set_focus().map_err(|e| e.to_string());
    }
    let origen = app
        .state::<Estado>()
        .origen
        .lock()
        .unwrap()
        .clone()
        .ok_or_else(|| "sin origen".to_string())?;
    crear_reunion(app, &origen)
}

/// Termina con la ventana (no con la X: esa solo la oculta).
pub fn cerrar_reunion(app: &AppHandle) {
    if let Some(w) = app.get_webview_window(ETIQUETA_REUNION) {
        let _ = w.destroy();
    }
}

fn crear_reunion(app: &AppHandle, origen: &str) -> Result<(), String> {
    let url = url_reunion(origen);
    let window = WebviewWindowBuilder::new(
        app,
        ETIQUETA_REUNION,
        WebviewUrl::External(url.parse().map_err(|_| "url inválida")?),
    )
    .title("Reunión — Colmena")
    .decorations(true)
    .resizable(true)
    .always_on_top(true)
    .visible(false)
    .inner_size(TAMANO_INICIAL.0, TAMANO_INICIAL.1)
    .min_inner_size(f64::from(ANCHO_MIN), f64::from(ALTO_MIN))
    .additional_browser_args(ARGS)
    .build()
    .map_err(|e| e.to_string())?;

    let monitores: Vec<Rect> = app.available_monitors().unwrap_or_default().iter().map(monitor_rect).collect();
    if let Some(v) = recordada(cfg_desde_app(app).reunion_ventana, &monitores) {
        let _ = window.set_size(tauri::PhysicalSize::new(v.ancho, v.alto));
        let _ = window.set_position(tauri::PhysicalPosition::new(v.x, v.y));
    }
    registrar_eventos_reunion(app, &window);
    // Si se comparte pantalla, la ventana sigue la misma regla que el notch durante la reunión.
    aplicar_visibilidad(app, cfg_desde_app(app).nudo.se_ve_al_compartir, crate::reunion::escuchando(app))?;
    window.show().map_err(|e| e.to_string())?;
    window.set_focus().map_err(|e| e.to_string())
}

/// La X solo oculta la ventana (la reunión sigue); moverla o cambiarle el tamaño se recuerda.
fn registrar_eventos_reunion(app: &AppHandle, window: &WebviewWindow) {
    let app_cl = app.clone();
    let window_cl = window.clone();
    let gen = Arc::new(AtomicU64::new(0));
    window.on_window_event(move |event| match event {
        WindowEvent::CloseRequested { api, .. } => {
            api.prevent_close();
            let _ = window_cl.hide();
        }
        WindowEvent::Moved(_) | WindowEvent::Resized(_) => programar_guardado_reunion(&app_cl, &window_cl, &gen),
        _ => {}
    });
}

fn programar_guardado_reunion(app: &AppHandle, window: &WebviewWindow, gen_atom: &Arc<AtomicU64>) {
    if window.is_minimized().unwrap_or(false) {
        return;
    }
    let (Ok(pos), Ok(tam)) = (window.outer_position(), window.inner_size()) else {
        return;
    };
    let v = VentanaGuardada { x: pos.x, y: pos.y, ancho: tam.width, alto: tam.height };
    let gen = gen_atom.fetch_add(1, Ordering::SeqCst) + 1;
    let gen_atom = Arc::clone(gen_atom);
    let ruta = app.state::<Estado>().ruta_config.clone();
    std::thread::spawn(move || {
        std::thread::sleep(Duration::from_millis(400));
        if gen_atom.load(Ordering::SeqCst) != gen {
            return;
        }
        let mut cfg = std::fs::read_to_string(&ruta).map(|t| leer_config(&t)).unwrap_or_default();
        cfg.reunion_ventana = Some(v);
        let _ = crate::escribir_config_archivo(&ruta, &colmena_nucleo::config::escribir_config(&cfg));
    });
}

pub const GLOBO_TAMANO: (f64, f64) = (280.0, 128.0);

pub fn crear_nudo(app: &AppHandle) -> Result<(), String> {
    let resultado = crear_nudo_ventanas(app);
    if resultado.is_err() {
        cerrar_nudo(app);
    }
    resultado
}

fn cerrar_nudo(app: &AppHandle) {
    for label in ["nudo", "nudo-globo"] {
        if let Some(w) = app.get_webview_window(label) {
            let _ = w.destroy();
        }
    }
}

fn crear_nudo_ventanas(app: &AppHandle) -> Result<(), String> {
    for (label, pagina, pasa_clics) in [("nudo", "nudo.html", true), ("nudo-globo", "nudo-globo.html", false)] {
        if app.get_webview_window(label).is_some() {
            continue;
        }
        let (ancho, alto) = if pasa_clics { (800.0, 600.0) } else { GLOBO_TAMANO };
        let w = WebviewWindowBuilder::new(app, label, WebviewUrl::App(pagina.into()))
            .visible(false)
            .decorations(false)
            .transparent(true)
            .always_on_top(true)
            .skip_taskbar(true)
            .focused(false)
            .focusable(false)
            .shadow(false)
            .resizable(false)
            .inner_size(ancho, alto)
            // WebView2 rechaza (0x8007139F) una ventana con argumentos distintos a los del resto de la app.
            .additional_browser_args(ARGS)
            .build()
            .map_err(|e| e.to_string())?;
        if pasa_clics {
            w.set_ignore_cursor_events(true).map_err(|e| e.to_string())?;
        }
        estilo_notch(&w, true)?;
    }
    aplicar_visibilidad(app, cfg_desde_app(app).nudo.se_ve_al_compartir, crate::reunion::escuchando(app))
}

/// Cubre el monitor con el overlay y pone el globo junto al objetivo (o cerca del origen del nudo).
pub fn ubicar_nudo(app: &AppHandle, monitor: &Monitor, objetivo: Option<&RectLogico>) -> Result<(), String> {
    let escala = monitor.scale_factor();
    let pos = monitor.position();
    let tam = monitor.size();
    let logico = (f64::from(tam.width) / escala, f64::from(tam.height) / escala);

    if let Some(w) = app.get_webview_window("nudo") {
        w.set_position(tauri::PhysicalPosition::new(pos.x, pos.y)).map_err(|e| e.to_string())?;
        w.set_size(tauri::PhysicalSize::new(tam.width, tam.height)).map_err(|e| e.to_string())?;
    }
    if let Some(g) = app.get_webview_window("nudo-globo") {
        let (ox, oy) = origen_nudo(logico);
        let (gx, gy) = match objetivo {
            Some(o) => {
                let mon = monitor_rect(monitor);
                let evitar: Vec<RectLogico> =
                    crate::uia::rects_efimeros().into_iter().filter_map(|r| a_overlay(r, mon, escala)).collect();
                posicion_globo_evitando(o, logico, GLOBO_TAMANO, &evitar)
            }
            None => (ox - GLOBO_TAMANO.0 + 32.0, oy - GLOBO_TAMANO.1 - 12.0),
        };
        let globo = RectLogico { x: gx, y: gy, ancho: GLOBO_TAMANO.0, alto: GLOBO_TAMANO.1 };
        let mira = objetivo.copied().unwrap_or(RectLogico { x: ox, y: oy, ancho: 0.0, alto: 0.0 });
        crate::nudo::guardar_lado_globo(app, lado_hacia(&globo, &mira));
        g.set_size(tauri::PhysicalSize::new(
            (GLOBO_TAMANO.0 * escala).round() as u32,
            (GLOBO_TAMANO.1 * escala).round() as u32,
        ))
        .map_err(|e| e.to_string())?;
        g.set_position(tauri::PhysicalPosition::new(
            pos.x + (gx * escala).round() as i32,
            pos.y + (gy * escala).round() as i32,
        ))
        .map_err(|e| e.to_string())?;
    }
    Ok(())
}

/// Con una reunión en curso el notch también se oculta al compartir, salvo que el interruptor diga que se vea.
pub fn aplicar_visibilidad(app: &AppHandle, se_ve: bool, escuchando: bool) -> Result<(), String> {
    for (label, visible) in colmena_nucleo::reunion::visibilidad::afinidades(escuchando, se_ve) {
        if let Some(w) = app.get_webview_window(label) {
            afinidad_pantalla(&w, visible)?;
        }
    }
    Ok(())
}

/// `set_content_protected` hace `SetWindowDisplayAffinity` en el hilo dueño de la ventana, sea cual sea el hilo que llame.
fn afinidad_pantalla(window: &WebviewWindow, se_ve: bool) -> Result<(), String> {
    window
        .set_content_protected(!se_ve)
        .map_err(|_| "no pude ocultar el nudo de la captura".to_string())
}

pub fn abrir_colmena_url(app: &AppHandle, url: &str) -> Result<(), String> {
    if let Some(window) = app.get_webview_window("colmena") {
        window
            .navigate(Url::parse(url).map_err(|_| "url inválida".to_string())?)
            .map_err(|e| e.to_string())?;
        window.show().map_err(|e| e.to_string())?;
        window.set_focus().map_err(|e| e.to_string())?;
        return Ok(());
    }

    let window = WebviewWindowBuilder::new(
        app,
        "colmena",
        WebviewUrl::External(url.parse().map_err(|_| "url inválida")?),
    )
    .title("Colmena")
    .inner_size(1280.0, 820.0)
    .additional_browser_args(ARGS)
    .build()
    .map_err(|e| e.to_string())?;

    let app_cl = app.clone();
    window.on_window_event(move |event| {
        if let tauri::WindowEvent::CloseRequested { api, .. } = event {
            api.prevent_close();
            if let Some(w) = app_cl.get_webview_window("colmena") {
                let _ = w.hide();
            }
        }
    });

    Ok(())
}

pub fn abrir_colmena_ventana(
    app: &AppHandle,
    origen: &str,
    sesion: Option<String>,
) -> Result<(), String> {
    let sid = sesion.as_deref();
    let url = url_colmena(origen, sid);
    abrir_colmena_url(app, &url)
}

pub fn notch_tamano_ventana(
    app: &AppHandle,
    window: &WebviewWindow,
    ancho: u32,
    alto: u32,
    foco: bool,
) -> Result<(), String> {
    ubicar_notch(app, window, ancho, alto)?;
    aplicar_foco(window, foco)
}

/// Ejecuta los pasos de `pasos_foco`. El último, `EnfocarContenido`, es el que faltaba: en Windows
/// `set_focus` activa la ventana nativa pero WebView2 no siempre le pasa el teclado a la página
/// (y si la ventana ya estaba al frente, tao ni siquiera la reactiva). `Webview::set_focus` hace el
/// `MoveFocus(PROGRAMMATIC)` del controlador. Los mensajes van al hilo principal en este orden.
fn aplicar_foco(window: &WebviewWindow, foco: bool) -> Result<(), String> {
    let visible = window.is_visible().unwrap_or(true);
    for paso in pasos_foco(visible, foco) {
        match paso {
            PasoFoco::Mostrar => window.show().map_err(|e| e.to_string())?,
            PasoFoco::PermitirActivar => estilo_notch(window, false)?,
            PasoFoco::ImpedirActivar => estilo_notch(window, true)?,
            PasoFoco::TraerAlFrente => window.set_focus().map_err(|e| e.to_string())?,
            PasoFoco::EnfocarContenido => {
                AsRef::<tauri::Webview>::as_ref(window).set_focus().map_err(|e| e.to_string())?
            }
        }
    }
    Ok(())
}

#[cfg(windows)]
pub(crate) fn notch_forma_ventana(window: &WebviewWindow, region: RegionFisica) -> Result<(), String> {
    use windows_sys::Win32::Foundation::HWND;
    use windows_sys::Win32::Graphics::Gdi::{CreateRoundRectRgn, DeleteObject, SetWindowRgn};

    let hwnd = window.hwnd().map_err(|e| e.to_string())?.0 as HWND;
    let rgn = unsafe {
        CreateRoundRectRgn(
            region.izquierda,
            region.arriba,
            region.derecha + 1,
            region.abajo + 1,
            region.diametro_esquina,
            region.diametro_esquina,
        )
    };
    if rgn.is_null() {
        return Err("no se pudo crear la región".into());
    }
    let ok = unsafe { SetWindowRgn(hwnd, rgn, 1) };
    if ok == 0 {
        unsafe {
            DeleteObject(rgn);
        }
        return Err("no se pudo aplicar la región".into());
    }
    Ok(())
}

#[cfg(not(windows))]
pub(crate) fn notch_forma_ventana(_window: &WebviewWindow, _region: RegionFisica) -> Result<(), String> {
    Ok(())
}

pub fn mostrar_notch_sin_foco(window: &WebviewWindow) -> Result<(), String> {
    if !window.is_visible().unwrap_or(true) {
        // El estilo va antes: con NOACTIVATE puesto, mostrarla no le roba el foco a la ventana de Ando.
        estilo_notch(window, true)?;
        window.show().map_err(|e| e.to_string())?;
    }
    Ok(())
}

/// Un menú o popup de otro programa (el ⋮ de Chrome) queda por encima de nuestras ventanas
/// "siempre arriba" porque el orden solo se fija al crearlas: lo vuelve a poner arriba.
/// Se llama desde el hilo del vigía; la ventana se toca en el hilo principal.
#[cfg(windows)]
pub fn reafirmar_arriba(app: &AppHandle) {
    let app_hilo = app.clone();
    let _ = app.run_on_main_thread(move || {
        use windows_sys::Win32::UI::WindowsAndMessaging::{
            SetWindowPos, HWND_TOPMOST, SWP_NOACTIVATE, SWP_NOMOVE, SWP_NOSIZE,
        };

        for label in ["notch", "reunion", "nudo", "nudo-globo"] {
            let Some(w) = app_hilo.get_webview_window(label) else {
                continue;
            };
            if !w.is_visible().unwrap_or(false) {
                continue;
            }
            let Ok(hwnd) = w.hwnd() else {
                continue;
            };
            unsafe {
                SetWindowPos(hwnd.0, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
            }
        }
    });
}

pub fn mostrar_notch_con_foco(window: &WebviewWindow) -> Result<(), String> {
    aplicar_foco(window, true)
}
