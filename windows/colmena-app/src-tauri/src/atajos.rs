use std::str::FromStr;

use colmena_nucleo::atajo_cambio::{decidir_cambio, CambioAtajo};
use colmena_nucleo::atajo_teclas::{armar_atajo, atajo_valido, duplicado_de};
use colmena_nucleo::config::{escribir_config, Accion, Atajos};
use colmena_nucleo::validar::es_url_local;
use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager, State, WebviewWindow};
use tauri_plugin_global_shortcut::{GlobalShortcutExt, Shortcut, ShortcutState};

use crate::{bandeja, leer_config_archivo, ventanas, Estado};

pub const EVENTO_NOTAS: &str = "notas-abrir";
pub const EVENTO_GUIA: &str = "guia-abrir";
pub const EVENTO_NOTCH_LISTO: &str = "notch-listo";

/// Qué atajo tiene cada acción y si el sistema lo tiene registrado ahora.
#[derive(Default)]
pub struct EstadoAtajos {
    /// El atajo que corresponde a cada acción (el último que se pudo registrar, o el guardado si nunca se pudo).
    pub activo: [String; Accion::TODAS.len()],
    /// Registrado en el sistema en este momento.
    pub registrado: [bool; Accion::TODAS.len()],
    /// El atajo guardado no se pudo registrar (lo usa otro programa).
    pub ocupado: [bool; Accion::TODAS.len()],
    /// Los atajos están soltados mientras la ventana "Atajos" graba una combinación.
    pub pausado: bool,
}

impl EstadoAtajos {
    pub fn desde(atajos: &Atajos) -> Self {
        let mut e = Self::default();
        for a in Accion::TODAS {
            e.activo[a.indice()] = atajos.get(a).to_string();
        }
        e
    }

    fn atajos(&self) -> Atajos {
        Atajos {
            notas: self.activo[Accion::Notas.indice()].clone(),
            notch: self.activo[Accion::Notch.indice()].clone(),
            colmena: self.activo[Accion::Colmena.indice()].clone(),
            guia: self.activo[Accion::Guia.indice()].clone(),
        }
    }
}

fn abrir_notas(app: &AppHandle) {
    let Some(w) = app.get_webview_window("notch") else {
        return;
    };
    let _ = ventanas::mostrar_notch_con_foco(&w);
    let emitir_ya = app.state::<Estado>().apertura_notas.lock().unwrap().pedir();
    if emitir_ya {
        let _ = app.emit_to("notch", EVENTO_NOTAS, ());
    }
}

fn abrir_guia(app: &AppHandle) {
    // Con un paso a la vista avanza como el botón del globo, sin mostrar ni activar ninguna ventana:
    // darle el foco a una ventana nuestra le cierra a Ando el menú que tenga abierto.
    if crate::nudo::atajo_guia_en_curso(app) {
        return;
    }
    let Some(w) = app.get_webview_window("notch") else {
        return;
    };
    // Sin paso: la cajita se abre con el foco, ahora que el atajo le da permiso a Colmena de pasar al frente.
    let _ = ventanas::mostrar_notch_con_foco(&w);
    let emitir_ya = app.state::<Estado>().apertura_guia.lock().unwrap().pedir();
    if emitir_ya {
        let _ = app.emit_to("notch", EVENTO_GUIA, ());
    }
}

/// El notch ya escucha: si algún atajo se apretó antes, abre ese modo ahora.
pub fn notch_listo(app: &AppHandle) {
    let estado = app.state::<Estado>();
    let notas = estado.apertura_notas.lock().unwrap().marcar_listo();
    let guia = estado.apertura_guia.lock().unwrap().marcar_listo();
    if notas {
        let _ = app.emit_to("notch", EVENTO_NOTAS, ());
    }
    if guia {
        let _ = app.emit_to("notch", EVENTO_GUIA, ());
    }
}

fn manejar(app: &AppHandle, accion: Accion) {
    match accion {
        Accion::Notas => abrir_notas(app),
        Accion::Notch => ventanas::alternar_notch(app),
        Accion::Colmena => ventanas::traer_colmena(app),
        Accion::Guia => abrir_guia(app),
    }
}

fn registrar_uno(app: &AppHandle, accion: Accion, atajo: &str) -> Result<(), String> {
    if !atajo_valido(atajo) {
        return Err("atajo inválido".into());
    }
    let shortcut = Shortcut::from_str(atajo).map_err(|e| e.to_string())?;
    app.global_shortcut()
        .on_shortcut(shortcut, move |app, _atajo, evento| {
            if evento.state() == ShortcutState::Pressed {
                manejar(app, accion);
            }
        })
        .map_err(|e| e.to_string())
}

fn soltar_uno(app: &AppHandle, atajo: &str) {
    if let Ok(shortcut) = Shortcut::from_str(atajo) {
        let _ = app.global_shortcut().unregister(shortcut);
    }
}

/// Registra los tres atajos guardados; el que esté ocupado queda marcado para la bandeja.
/// Nunca se sostiene el lock mientras se registra: el plugin puede esperar al hilo principal.
pub fn arrancar(app: &AppHandle, atajos: &Atajos) {
    let estado = app.state::<Estado>();
    for a in Accion::TODAS {
        let i = a.indice();
        let atajo = atajos.get(a);
        let ya = {
            let e = estado.atajos.lock().unwrap();
            e.registrado[i] && e.activo[i] == atajo
        };
        let ok = ya || registrar_uno(app, a, atajo).is_ok();
        let mut e = estado.atajos.lock().unwrap();
        e.activo[i] = atajo.to_string();
        e.registrado[i] = ok;
        e.ocupado[i] = !ok;
    }
    bandeja::refrescar_atajos(app);
}

/// Cambia el atajo de una acción sin tocar los otros. Un atajo que no se pudo registrar no pisa al anterior.
pub fn cambiar(app: &AppHandle, accion: Accion, nuevo: &str) -> Result<CambioAtajo, String> {
    if !atajo_valido(nuevo) {
        return Err("Esa combinación no sirve".into());
    }
    let estado = app.state::<Estado>();
    let i = accion.indice();
    let (anterior, registrado, pausado, actuales) = {
        let e = estado.atajos.lock().unwrap();
        (e.activo[i].clone(), e.registrado[i], e.pausado, e.atajos())
    };
    if let Some(otra) = duplicado_de(&actuales, accion, nuevo) {
        return Err(format!("Ya lo usa {}", otra.nombre()));
    }
    if nuevo == anterior && registrado {
        return Ok(decidir_cambio(&anterior, nuevo, true));
    }
    let ok = registrar_uno(app, accion, nuevo).is_ok();
    // En pausa solo se prueba que esté libre; los registra `reanudar`.
    if ok && pausado {
        soltar_uno(app, nuevo);
    }
    let cambio = decidir_cambio(&anterior, nuevo, ok);
    if ok && registrado && anterior != nuevo {
        soltar_uno(app, &anterior);
    }
    {
        let mut e = estado.atajos.lock().unwrap();
        e.activo[i] = cambio.activo.clone();
        if ok {
            e.registrado[i] = !pausado;
            e.ocupado[i] = false;
        }
    }
    bandeja::refrescar_atajos(app);
    Ok(cambio)
}

/// Suelta todos los atajos para que la ventana "Atajos" reciba las teclas.
pub fn pausar(app: &AppHandle) {
    let estado = app.state::<Estado>();
    let a_soltar: Vec<String> = {
        let mut e = estado.atajos.lock().unwrap();
        if e.pausado {
            return;
        }
        e.pausado = true;
        let lista = Accion::TODAS
            .into_iter()
            .filter(|a| e.registrado[a.indice()])
            .map(|a| e.activo[a.indice()].clone())
            .collect();
        e.registrado = [false; Accion::TODAS.len()];
        lista
    };
    for atajo in a_soltar {
        soltar_uno(app, &atajo);
    }
}

/// Vuelve a registrar todos. Si ya estaban, no hace nada.
pub fn reanudar(app: &AppHandle) {
    let estado = app.state::<Estado>();
    let activos: Vec<(Accion, String)> = {
        let mut e = estado.atajos.lock().unwrap();
        if !e.pausado {
            return;
        }
        e.pausado = false;
        Accion::TODAS
            .into_iter()
            .map(|a| (a, e.activo[a.indice()].clone()))
            .collect()
    };
    for (a, atajo) in activos {
        let ok = registrar_uno(app, a, &atajo).is_ok();
        let mut e = estado.atajos.lock().unwrap();
        e.registrado[a.indice()] = ok;
        e.ocupado[a.indice()] = !ok;
    }
    bandeja::refrescar_atajos(app);
}

#[derive(Serialize)]
pub struct Fila {
    pub accion: &'static str,
    pub nombre: &'static str,
    pub atajo: String,
    pub defecto: &'static str,
    pub ocupado: bool,
}

fn filas(estado: &Estado) -> Vec<Fila> {
    let e = estado.atajos.lock().unwrap();
    Accion::TODAS
        .into_iter()
        .map(|a| Fila {
            accion: a.clave(),
            nombre: a.nombre(),
            atajo: e.activo[a.indice()].clone(),
            defecto: a.default_atajo(),
            ocupado: e.ocupado[a.indice()],
        })
        .collect()
}

fn exige_atajos(window: &WebviewWindow) -> Result<(), String> {
    if window.label() != "atajos" {
        return Err("no permitido".into());
    }
    let url = window.url().map_err(|_| "no permitido".to_string())?;
    if !es_url_local(url.as_str()) {
        return Err("no permitido".into());
    }
    Ok(())
}

fn accion_de(clave: &str) -> Result<Accion, String> {
    Accion::desde_clave(clave).ok_or_else(|| "acción inválida".to_string())
}

#[tauri::command]
pub fn leer_atajos(window: WebviewWindow, estado: State<'_, Estado>) -> Result<Vec<Fila>, String> {
    exige_atajos(&window)?;
    Ok(filas(&estado))
}

#[tauri::command]
pub fn pausar_atajos(app: AppHandle, window: WebviewWindow) -> Result<(), String> {
    exige_atajos(&window)?;
    pausar(&app);
    Ok(())
}

#[tauri::command]
pub fn reanudar_atajos(app: AppHandle, window: WebviewWindow) -> Result<(), String> {
    exige_atajos(&window)?;
    reanudar(&app);
    Ok(())
}

/// Arma la combinación grabada y avisa si no sirve o ya la usa otra acción.
#[tauri::command]
pub fn probar_atajo(
    window: WebviewWindow,
    estado: State<'_, Estado>,
    accion: String,
    ctrl: bool,
    alt: bool,
    shift: bool,
    code: String,
) -> Result<String, String> {
    exige_atajos(&window)?;
    let accion = accion_de(&accion)?;
    let atajo = armar_atajo(ctrl, alt, shift, &code)?;
    let actuales = estado.atajos.lock().unwrap().atajos();
    if let Some(otra) = duplicado_de(&actuales, accion, &atajo) {
        return Err(format!("Ya lo usa {}", otra.nombre()));
    }
    Ok(atajo)
}

#[tauri::command]
pub fn guardar_atajo(
    app: AppHandle,
    window: WebviewWindow,
    estado: State<'_, Estado>,
    accion: String,
    atajo: String,
) -> Result<Vec<Fila>, String> {
    exige_atajos(&window)?;
    let accion = accion_de(&accion)?;
    let cambio = cambiar(&app, accion, &atajo)?;
    if cambio.ocupado {
        return Err(format!("Lo usa otro programa: queda {}", cambio.activo));
    }
    if cambio.guardar {
        let mut cfg = leer_config_archivo(&estado.ruta_config);
        cfg.atajos.set(accion, &cambio.activo);
        crate::escribir_config_archivo(&estado.ruta_config, &escribir_config(&cfg)).map_err(|e| e.to_string())?;
    }
    Ok(filas(&estado))
}
