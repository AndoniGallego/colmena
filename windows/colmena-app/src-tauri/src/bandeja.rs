use std::sync::atomic::Ordering;

use colmena_nucleo::atajo_cambio::{aviso_ocupado, linea_bandeja};
use colmena_nucleo::config::{escribir_config, leer_config, Accion, Config};
use tauri::{
    menu::{CheckMenuItem, Menu, MenuItem, PredefinedMenuItem, Submenu},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Manager, Monitor, Wry,
};
use tauri_plugin_autostart::ManagerExt;

use crate::ventanas;
use crate::Estado;

fn leer_cfg(estado: &Estado) -> Config {
    std::fs::read_to_string(&estado.ruta_config)
        .map(|t| leer_config(&t))
        .unwrap_or_default()
}

fn guardar_arranque(estado: &Estado, arranque: bool) -> Result<(), String> {
    let mut cfg = leer_cfg(estado);
    cfg.arranque = arranque;
    std::fs::write(&estado.ruta_config, escribir_config(&cfg)).map_err(|e| e.to_string())
}

fn guardar_monitor(estado: &Estado, nombre: &str) -> Result<(), String> {
    let mut cfg = leer_cfg(estado);
    cfg.monitor = Some(nombre.to_string());
    estado.ancla_guardado_gen.fetch_add(1, Ordering::SeqCst);
    cfg.ancla = None;
    *estado.ancla.lock().unwrap() = None;
    std::fs::write(&estado.ruta_config, escribir_config(&cfg)).map_err(|e| e.to_string())
}

const ID_CAMBIAR_ATAJOS: &str = "cambiar_atajos";

/// Reescribe el submenú "Atajos": un renglón gris por acción, el aviso de los ocupados y "Cambiar atajos…".
pub fn refrescar_atajos(app: &AppHandle) {
    let estado = app.state::<Estado>();
    let (activos, ocupados) = {
        let e = estado.atajos.lock().unwrap();
        (e.activo.clone(), e.ocupado)
    };
    let Some(sub) = estado.atajo_submenu.lock().unwrap().clone() else {
        return;
    };
    if let Ok(items) = sub.items() {
        for item in items {
            let _ = sub.remove(&item);
        }
    }
    for a in Accion::TODAS {
        if let Ok(item) = MenuItem::with_id(
            app,
            format!("atajo_linea:{}", a.clave()),
            linea_bandeja(a, &activos[a.indice()]),
            false,
            None::<&str>,
        ) {
            let _ = sub.append(&item);
        }
    }
    let mut aviso_tooltip: Option<String> = None;
    for a in Accion::TODAS {
        if ocupados[a.indice()] {
            let texto = aviso_ocupado(a);
            if let Ok(item) = MenuItem::with_id(
                app,
                format!("atajo_aviso:{}", a.clave()),
                &texto,
                false,
                None::<&str>,
            ) {
                let _ = sub.append(&item);
            }
            aviso_tooltip.get_or_insert(texto);
        }
    }
    if let Ok(sep) = PredefinedMenuItem::separator(app) {
        let _ = sub.append(&sep);
    }
    if let Ok(item) = MenuItem::with_id(app, ID_CAMBIAR_ATAJOS, "Cambiar atajos…", true, None::<&str>) {
        let _ = sub.append(&item);
    }
    if let Some(tray) = app.tray_by_id("colmena") {
        let _ = tray.set_tooltip(aviso_tooltip.as_deref());
    }
}

fn indice_monitor_elegido(app: &AppHandle, cfg: &Config) -> usize {
    let Ok(monitors) = app.available_monitors() else {
        return 0;
    };
    if monitors.is_empty() {
        return 0;
    }
    if let Some(ref wanted) = cfg.monitor {
        if let Some(i) = monitors
            .iter()
            .position(|m| m.name().map(|n| n == wanted).unwrap_or(false))
        {
            return i;
        }
    }
    if let Ok(Some(primary)) = app.primary_monitor() {
        if let Some(i) = monitors.iter().position(|m| ventanas::monitors_iguales(m, &primary)) {
            return i;
        }
    }
    0
}

fn sincronizar_checks_monitor(app: &AppHandle, estado: &Estado) {
    let cfg = leer_cfg(estado);
    let elegido = indice_monitor_elegido(app, &cfg);
    let checks = estado.monitor_checks.lock().unwrap();
    for (i, item) in checks.iter().enumerate() {
        let _ = item.set_checked(i == elegido);
    }
}

fn rotulo_monitor(app: &AppHandle, idx: usize, m: &Monitor) -> String {
    let n = idx + 1;
    let w = m.size().width;
    let h = m.size().height;
    let mut s = format!("Monitor {n} ({w}x{h})");
    if app
        .primary_monitor()
        .ok()
        .flatten()
        .is_some_and(|p| ventanas::monitors_iguales(m, &p))
    {
        s.push_str(" · principal");
    }
    s
}

fn construir_submenu_monitor(
    app: &AppHandle,
    cfg: &Config,
) -> Result<(Submenu<Wry>, Vec<CheckMenuItem<Wry>>), String> {
    let monitors = app
        .available_monitors()
        .map_err(|e| e.to_string())?;
    let elegido = indice_monitor_elegido(app, cfg);
    let mut checks = Vec::new();
    let mut refs: Vec<&dyn tauri::menu::IsMenuItem<Wry>> = Vec::new();

    for (i, m) in monitors.iter().enumerate() {
        let id = format!("monitor:{i}");
        let item = CheckMenuItem::with_id(
            app,
            id,
            rotulo_monitor(app, i, m),
            true,
            i == elegido,
            None::<&str>,
        )
        .map_err(|e| e.to_string())?;
        checks.push(item);
    }

    for item in &checks {
        refs.push(item);
    }

    let submenu = Submenu::with_id_and_items(app, "monitores", "Monitor del notch", true, &refs)
        .map_err(|e| e.to_string())?;
    Ok((submenu, checks))
}

pub fn aplicar_arranque(app: &AppHandle, cfg: &Config) {
    let autolaunch = app.autolaunch();
    if cfg.arranque {
        let _ = autolaunch.enable();
    } else {
        let _ = autolaunch.disable();
    }
}

pub fn inicializar(app: &AppHandle, estado: &Estado) -> Result<(), String> {
    let cfg = leer_cfg(estado);
    let arranque_item = CheckMenuItem::with_id(app, "arranque", "Arrancar con Windows", true, cfg.arranque, None::<&str>)
        .map_err(|e| e.to_string())?;
    let toggle_notch = MenuItem::with_id(app, "toggle_notch", "Mostrar u ocultar el notch", true, None::<&str>)
        .map_err(|e| e.to_string())?;
    let abrir = MenuItem::with_id(app, "abrir_colmena", "Abrir Colmena", true, None::<&str>)
        .map_err(|e| e.to_string())?;
    let entornos = MenuItem::with_id(app, "entornos", "Entornos", true, None::<&str>)
        .map_err(|e| e.to_string())?;
    let notebook = MenuItem::with_id(app, "notebook", "Dirección de la notebook…", true, None::<&str>)
        .map_err(|e| e.to_string())?;
    let cambiar = MenuItem::with_id(app, "cambiar_origen", "Cambiar dirección…", true, None::<&str>)
        .map_err(|e| e.to_string())?;
    let salir = MenuItem::with_id(app, "salir", "Salir", true, None::<&str>)
        .map_err(|e| e.to_string())?;

    let (submenu_monitor, monitor_checks) = construir_submenu_monitor(app, &cfg)?;
    *estado.monitor_checks.lock().unwrap() = monitor_checks;
    let submenu_atajo = Submenu::with_id(app, "atajos", "Atajos", true).map_err(|e| e.to_string())?;
    *estado.atajo_submenu.lock().unwrap() = Some(submenu_atajo.clone());
    refrescar_atajos(app);

    let menu = Menu::with_items(
        app,
        &[
            &toggle_notch,
            &abrir,
            &entornos,
            &arranque_item,
            &PredefinedMenuItem::separator(app).map_err(|e| e.to_string())?,
            &submenu_monitor,
            &submenu_atajo,
            &PredefinedMenuItem::separator(app).map_err(|e| e.to_string())?,
            &notebook,
            &cambiar,
            &salir,
        ],
    )
    .map_err(|e| e.to_string())?;

    let icon = app
        .default_window_icon()
        .ok_or("sin ícono")?
        .clone();

    TrayIconBuilder::with_id("colmena")
        .icon(icon)
        .menu(&menu)
        .on_menu_event(move |app, event| {
            let id = event.id().as_ref();
            if let Some(rest) = id.strip_prefix("monitor:") {
                let Ok(idx) = rest.parse::<usize>() else {
                    return;
                };
                let estado = app.state::<Estado>();
                let monitors = match app.available_monitors() {
                    Ok(m) => m,
                    Err(_) => return,
                };
                let Some(monitor) = monitors.get(idx) else {
                    return;
                };
                let Some(nombre) = monitor.name().cloned() else {
                    let mut cfg = leer_cfg(&estado);
                    cfg.monitor = None;
                    estado.ancla_guardado_gen.fetch_add(1, Ordering::SeqCst);
                    cfg.ancla = None;
                    *estado.ancla.lock().unwrap() = None;
                    let _ = std::fs::write(&estado.ruta_config, escribir_config(&cfg));
                    sincronizar_checks_monitor(app, &estado);
                    let _ = ventanas::reposicionar_notch_actual(app);
                    return;
                };
                let _ = guardar_monitor(&estado, &nombre);
                sincronizar_checks_monitor(app, &estado);
                let _ = ventanas::reposicionar_notch_actual(app);
                return;
            }

            match id {
                "toggle_notch" => ventanas::alternar_notch(app),
                ID_CAMBIAR_ATAJOS => {
                    let _ = ventanas::crear_atajos(app);
                }
                "abrir_colmena" => {
                    let estado = app.state::<Estado>();
                    let origen = estado.origen.lock().unwrap().clone();
                    if let Some(o) = origen {
                        let _ = ventanas::abrir_colmena_ventana(app, &o, None);
                    }
                }
                "entornos" => {
                    let estado = app.state::<Estado>();
                    let origen = estado.origen.lock().unwrap().clone();
                    if let Some(o) = origen {
                        let _ = crate::entornos::abrir_entornos_desde_bandeja(app, &o);
                    }
                }
                "notebook" => {
                    let _ = ventanas::crear_notebook(app);
                }
                "arranque" => {
                    let estado = app.state::<Estado>();
                    let cfg = leer_cfg(&estado);
                    let nuevo = !cfg.arranque;
                    let _ = guardar_arranque(&estado, nuevo);
                    aplicar_arranque(
                        app,
                        &Config {
                            arranque: nuevo,
                            ..cfg
                        },
                    );
                }
                "cambiar_origen" => {
                    let _ = ventanas::crear_origen(app);
                }
                "salir" => {
                    app.exit(0);
                }
                _ => {}
            }
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                let app = tray.app_handle();
                if let Some(w) = app.get_webview_window("colmena") {
                    let _ = w.show();
                    let _ = w.set_focus();
                } else if let Some(w) = app.get_webview_window("notch") {
                    let _ = w.show();
                }
            }
        })
        .build(app)
        .map_err(|e| e.to_string())?;

    Ok(())
}
