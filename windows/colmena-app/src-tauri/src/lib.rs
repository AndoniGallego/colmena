mod atajos;
mod bandeja;
mod entornos;
mod tuneles;
mod ventanas;

use colmena_nucleo::config::{escribir_config, leer_config, Config};
use colmena_nucleo::notas_pendiente::AperturaNotas;
use colmena_nucleo::posicion::Ancla;
use colmena_nucleo::validar::{
    es_url_local, mismo_origen, validar_aviso, validar_origen, validar_sesion, validar_tamano,
};
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;
use tauri::ipc::CapabilityBuilder;
use tauri::menu::CheckMenuItem;
use tauri::{AppHandle, Listener, Manager, RunEvent, State, WebviewWindow, Wry};
use tauri_plugin_autostart::MacosLauncher;

pub struct Estado {
    pub origen: Mutex<Option<String>>,
    pub ruta_config: PathBuf,
    pub monitor_checks: Mutex<Vec<CheckMenuItem<Wry>>>,
    pub atajo_submenu: Mutex<Option<tauri::menu::Submenu<Wry>>>,
    pub atajos: Mutex<atajos::EstadoAtajos>,
    pub ancla: Mutex<Option<Ancla>>,
    pub ultima_pos: Mutex<Option<(i32, i32)>>,
    pub ancla_guardado_gen: Arc<AtomicU64>,
    pub tuneles: tuneles::Tuneles,
    pub apertura_notas: Mutex<AperturaNotas>,
}

pub(crate) fn programar_guardado_ancla(estado: &Estado, ancla: Option<Ancla>) {
    let gen_atom = Arc::clone(&estado.ancla_guardado_gen);
    let gen = gen_atom.fetch_add(1, Ordering::SeqCst) + 1;
    let ruta = estado.ruta_config.clone();
    std::thread::spawn(move || {
        std::thread::sleep(Duration::from_millis(400));
        if gen_atom.load(Ordering::SeqCst) != gen {
            return;
        }
        let mut cfg = std::fs::read_to_string(&ruta)
            .map(|t| leer_config(&t))
            .unwrap_or_default();
        cfg.ancla = ancla;
        let _ = std::fs::write(&ruta, escribir_config(&cfg));
    });
}

fn leer_config_archivo(ruta: &PathBuf) -> Config {
    std::fs::read_to_string(ruta)
        .map(|t| leer_config(&t))
        .unwrap_or_default()
}

pub(crate) fn exige_ventana(
    window: &WebviewWindow,
    estado: &Estado,
    label: &str,
) -> Result<String, String> {
    if window.label() != label {
        return Err("no permitido".into());
    }
    let origen = estado
        .origen
        .lock()
        .unwrap()
        .clone()
        .ok_or_else(|| "no permitido".to_string())?;
    let url = window.url().map_err(|_| "no permitido".to_string())?;
    if !mismo_origen(url.as_str(), &origen) {
        return Err("no permitido".into());
    }
    Ok(origen)
}

fn exige_notch(window: &WebviewWindow, estado: &Estado) -> Result<String, String> {
    exige_ventana(window, estado, "notch")
}

pub fn arrancar(app: &AppHandle, estado: &Estado) -> Result<(), String> {
    let origen = estado
        .origen
        .lock()
        .unwrap()
        .clone()
        .ok_or_else(|| "sin origen".to_string())?;

    app.add_capability(
        CapabilityBuilder::new("notch-remoto")
            .remote(format!("{origen}/*"))
            .local(false)
            .window("notch")
            .permission("allow-notch-tamano")
            .permission("allow-abrir-colmena")
            .permission("allow-mostrar-aviso")
            .permission("allow-notch-arrastrar")
            .permission("allow-notch-forma")
            .permission("core:event:allow-listen")
            .permission("core:event:allow-emit"),
    )
    .map_err(|e| e.to_string())?;

    app.add_capability(
        CapabilityBuilder::new("entornos-remoto")
            .remote(format!("{origen}/*"))
            .local(false)
            .window("colmena")
            .permission("allow-entorno-abrir")
            .permission("allow-entorno-cerrar")
            .permission("allow-entornos-estado")
            .permission("allow-abrir-ajuste-notebook"),
    )
    .map_err(|e| e.to_string())?;

    if app.get_webview_window("notch").is_none() {
        ventanas::crear_notch(app, &origen)?;
    }

    let cfg = leer_config_archivo(&estado.ruta_config);
    bandeja::aplicar_arranque(app, &cfg);
    atajos::arrancar(app, &cfg.atajos);
    Ok(())
}

#[tauri::command]
fn notch_arrastrar(window: WebviewWindow, estado: State<'_, Estado>) -> Result<(), String> {
    exige_notch(&window, &estado)?;
    window.start_dragging().map_err(|e| e.to_string())
}

#[tauri::command]
fn notch_tamano(
    app: AppHandle,
    window: WebviewWindow,
    estado: State<'_, Estado>,
    ancho: u32,
    alto: u32,
    foco: bool,
) -> Result<(), String> {
    exige_notch(&window, &estado)?;
    let (ancho, alto) = validar_tamano(ancho, alto)?;
    ventanas::notch_tamano_ventana(&app, &window, ancho, alto, foco)
}

#[tauri::command]
fn notch_forma(
    window: WebviewWindow,
    estado: State<'_, Estado>,
    x: f64,
    y: f64,
    ancho: f64,
    alto: f64,
    radio: f64,
) -> Result<(), String> {
    exige_notch(&window, &estado)?;
    let factor = window.scale_factor().map_err(|e| e.to_string())?;
    let inner = window.inner_size().map_err(|e| e.to_string())?;
    let region = colmena_nucleo::forma::region_desde_pastilla(
        x,
        y,
        ancho,
        alto,
        radio,
        factor,
        inner.width,
        inner.height,
    )?;
    ventanas::notch_forma_ventana(&window, region)
}

// async: crear ventanas desde un comando sync bloquea el hilo principal en Windows (wry#583).
#[tauri::command]
async fn abrir_colmena(
    app: AppHandle,
    window: WebviewWindow,
    estado: State<'_, Estado>,
    sesion: Option<String>,
) -> Result<(), String> {
    let origen = exige_notch(&window, &estado)?;
    let sid = sesion.filter(|s| validar_sesion(s));
    ventanas::abrir_colmena_ventana(&app, &origen, sid)
}

#[tauri::command]
fn mostrar_aviso(
    window: WebviewWindow,
    estado: State<'_, Estado>,
    tipo: String,
) -> Result<(), String> {
    exige_notch(&window, &estado)?;
    if !validar_aviso(&tipo) {
        return Err("aviso inválido".into());
    }
    ventanas::mostrar_notch_sin_foco(&window)
}

// async: arrancar crea el webview notch; desde un comando sync en Windows cuelga la UI (wry#583).
#[tauri::command]
async fn guardar_origen(
    app: AppHandle,
    window: WebviewWindow,
    estado: State<'_, Estado>,
    origen: String,
) -> Result<(), String> {
    if window.label() != "origen" {
        return Err("no permitido".into());
    }
    let url = window.url().map_err(|_| "no permitido".to_string())?;
    if !es_url_local(url.as_str()) {
        return Err("no permitido".into());
    }

    let nuevo = validar_origen(&origen)?;
    let had = {
        let guard = estado.origen.lock().unwrap();
        guard.is_some()
    };

    let mut cfg = leer_config_archivo(&estado.ruta_config);
    cfg.origen = Some(nuevo.clone());
    std::fs::write(&estado.ruta_config, escribir_config(&cfg)).map_err(|e| e.to_string())?;
    *estado.origen.lock().unwrap() = Some(nuevo);

    if had {
        return Err("Reiniciá el programa para que tome la nueva dirección.".into());
    }

    arrancar(&app, &estado)?;
    if window.close().is_err() {
        let _ = window.destroy();
    }
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            if let Some(w) = app.get_webview_window("colmena") {
                let _ = w.show();
                let _ = w.set_focus();
            } else if let Some(w) = app.get_webview_window("notch") {
                let _ = w.show();
            }
        }))
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .plugin(tauri_plugin_autostart::init(
            MacosLauncher::LaunchAgent,
            None,
        ))
        .plugin(
            tauri_plugin_opener::Builder::new()
                .open_js_links_on_click(false)
                .build(),
        )
        .invoke_handler(tauri::generate_handler![
            notch_tamano,
            notch_forma,
            notch_arrastrar,
            abrir_colmena,
            mostrar_aviso,
            guardar_origen,
            entornos::entorno_abrir,
            entornos::entorno_cerrar,
            entornos::entornos_estado,
            entornos::abrir_ajuste_notebook,
            entornos::leer_notebook,
            entornos::guardar_notebook,
            atajos::leer_atajos,
            atajos::pausar_atajos,
            atajos::reanudar_atajos,
            atajos::probar_atajo,
            atajos::guardar_atajo
        ])
        .setup(|app| {
            let config_dir = app.path().app_config_dir().map_err(|e| e.to_string())?;
            std::fs::create_dir_all(&config_dir).map_err(|e| e.to_string())?;
            let ruta_config = config_dir.join("config.json");
            let cfg = leer_config_archivo(&ruta_config);
            let origen = cfg.origen.clone();

            app.manage(Estado {
                origen: Mutex::new(origen.clone()),
                ruta_config,
                monitor_checks: Mutex::new(Vec::new()),
                atajo_submenu: Mutex::new(None),
                atajos: Mutex::new(atajos::EstadoAtajos::desde(&cfg.atajos)),
                ancla: Mutex::new(cfg.ancla),
                ultima_pos: Mutex::new(None),
                ancla_guardado_gen: Arc::new(AtomicU64::new(0)),
                tuneles: Default::default(),
                apertura_notas: Mutex::new(AperturaNotas::default()),
            });

            let handle = app.handle().clone();
            let para_listo = handle.clone();
            handle.listen(atajos::EVENTO_NOTCH_LISTO, move |_| {
                atajos::notch_listo(&para_listo);
            });
            let estado = app.state::<Estado>();
            bandeja::inicializar(&handle, &estado)?;

            if origen.is_none() {
                ventanas::crear_origen(&handle)?;
            } else {
                arrancar(&handle, &estado)?;
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error al arrancar")
        .run(|app, evento| {
            if let RunEvent::Exit = evento {
                if let Some(e) = app.try_state::<Estado>() {
                    e.tuneles.cerrar_todos();
                }
            }
        });
}
