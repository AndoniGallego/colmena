use colmena_nucleo::config::leer_config;
use colmena_nucleo::forma::RegionFisica;
use colmena_nucleo::posicion::{ancla_de, encajar, monitor_de, Rect};
use colmena_nucleo::validar::{url_colmena, url_notch, x_centrada};
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
    estilo_notch(window, !foco)?;
    if foco {
        window.set_focus().map_err(|e| e.to_string())?;
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
        window.show().map_err(|e| e.to_string())?;
        estilo_notch(window, true)?;
    }
    Ok(())
}

pub fn mostrar_notch_con_foco(window: &WebviewWindow) -> Result<(), String> {
    if !window.is_visible().unwrap_or(true) {
        window.show().map_err(|e| e.to_string())?;
    }
    estilo_notch(window, false)?;
    window.set_focus().map_err(|e| e.to_string())
}
