use std::sync::atomic::{AtomicIsize, Ordering};
use std::sync::mpsc::{Receiver, Sender};
use std::sync::{Arc, Mutex, OnceLock};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use colmena_nucleo::nudo::controles::{
    filtrar_y_numerar, necesita_reintento, Candidato, ControlListado, PRESUPUESTO_MS,
    PRESUPUESTO_REINTENTO_MS, TOPE_CONTROLES,
};
use colmena_nucleo::nudo::coords::a_overlay;
use colmena_nucleo::nudo::orden::foto_vigente;
use colmena_nucleo::nudo::pc::{
    codigo_de_error, cuenta_como_expandido, es_efimera, popups_de_la_guardada, rect_utilizable, ventana_de_sistema,
    Guardada, VentanaListada, VentanaNueva,
};
use colmena_nucleo::nudo::{ERR_FALLO_PC, ERR_FOTO_VIEJA, ERR_SIN_CONTROL, ERR_SIN_CONTROLES, ERR_SIN_VENTANA};
use colmena_nucleo::posicion::{monitor_de, Ancla, Rect};
use tauri::{AppHandle, Manager};
use windows::core::{implement, Ref, BOOL, PWSTR};
use windows::Win32::Foundation::{CloseHandle, HWND, LPARAM, RECT};
use windows::Win32::Graphics::Dwm::{DwmGetWindowAttribute, DWMWA_EXTENDED_FRAME_BOUNDS};
use windows::Win32::System::Com::{CoCreateInstance, CoInitializeEx, CLSCTX_INPROC_SERVER, COINIT_MULTITHREADED};
use windows::Win32::System::Threading::{
    OpenProcess, QueryFullProcessImageNameW, PROCESS_NAME_WIN32, PROCESS_QUERY_LIMITED_INFORMATION,
};
use windows::Win32::UI::Accessibility::{
    CUIAutomation, IUIAutomation, IUIAutomationCacheRequest, IUIAutomationElement,
    IUIAutomationEventHandler, IUIAutomationEventHandler_Impl,
    IUIAutomationFocusChangedEventHandler, IUIAutomationFocusChangedEventHandler_Impl,
    IUIAutomationPropertyChangedEventHandler, IUIAutomationPropertyChangedEventHandler_Impl,
    IUIAutomationTreeWalker, SetWinEventHook, TreeScope_Element, HWINEVENTHOOK,
    UIA_BoundingRectanglePropertyId, UIA_ControlTypePropertyId, UIA_EVENT_ID,
    UIA_ExpandCollapseExpandCollapseStatePropertyId, UIA_Invoke_InvokedEventId, UIA_IsEnabledPropertyId,
    UIA_IsOffscreenPropertyId, UIA_IsPasswordPropertyId, UIA_NamePropertyId, UIA_PROPERTY_ID,
};
use windows::Win32::System::Variant::VARIANT;
use windows::Win32::UI::WindowsAndMessaging::{
    DispatchMessageW, EnumWindows, GetAncestor, GetClassNameW, GetForegroundWindow, GetMessageW, GetWindow,
    GetWindowLongPtrW, GetWindowRect, GetWindowTextW, GetWindowThreadProcessId, IsIconic, IsWindow,
    IsWindowVisible, TranslateMessage, EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_MENUPOPUPSTART,
    GA_ROOT, GA_ROOTOWNER, GWL_EXSTYLE, GWL_STYLE, GW_OWNER, MSG, WINEVENT_OUTOFCONTEXT,
    WINEVENT_SKIPOWNPROCESS, WS_CAPTION, WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW,
};

use super::{Lectura, PedidoUia};

const MAX_NODOS: usize = 3000;
const MAX_PROFUNDIDAD: usize = 64;

pub struct LecturaCruda {
    pub titulo: String,
    pub proceso: String,
    pub rect_ventana: Rect,
    pub candidatos: Vec<Candidato>,
    pub elementos: Vec<IUIAutomationElement>,
    pub crudos: usize,
    pub ms: u128,
}

pub fn crear_automation() -> Result<IUIAutomation, String> {
    unsafe {
        // S_FALSE (ya iniciado) y RPC_E_CHANGED_MODE no impiden usar UIA en este hilo.
        let _ = CoInitializeEx(None, COINIT_MULTITHREADED);
        CoCreateInstance(&CUIAutomation, None, CLSCTX_INPROC_SERVER).map_err(|e| e.to_string())
    }
}

fn rect_de(r: RECT) -> Rect {
    Rect {
        x: r.left,
        y: r.top,
        ancho: (r.right - r.left).max(0) as u32,
        alto: (r.bottom - r.top).max(0) as u32,
    }
}

fn pedido_cache(auto: &IUIAutomation) -> Result<IUIAutomationCacheRequest, String> {
    unsafe {
        let c = auto.CreateCacheRequest().map_err(|e| e.to_string())?;
        for p in [
            UIA_ControlTypePropertyId,
            UIA_NamePropertyId,
            UIA_BoundingRectanglePropertyId,
            UIA_IsOffscreenPropertyId,
            UIA_IsEnabledPropertyId,
            UIA_IsPasswordPropertyId,
        ] {
            c.AddProperty(p).map_err(|e| e.to_string())?;
        }
        c.SetTreeScope(TreeScope_Element).map_err(|e| e.to_string())?;
        Ok(c)
    }
}

fn candidato_de(el: &IUIAutomationElement) -> Option<Candidato> {
    unsafe {
        Some(Candidato {
            tipo_uia: el.CachedControlType().ok()?.0,
            nombre: el.CachedName().map(|b| b.to_string()).unwrap_or_default(),
            rect: rect_de(el.CachedBoundingRectangle().ok()?),
            fuera_de_pantalla: el.CachedIsOffscreen().map(|b| b.as_bool()).unwrap_or(true),
            habilitado: el.CachedIsEnabled().map(|b| b.as_bool()).unwrap_or(false),
            es_password: el.CachedIsPassword().map(|b| b.as_bool()).unwrap_or(true),
        })
    }
}

struct Recorrido<'a> {
    caminante: &'a IUIAutomationTreeWalker,
    cache: &'a IUIAutomationCacheRequest,
    limite: Instant,
    crudos: usize,
    candidatos: Vec<Candidato>,
    elementos: Vec<IUIAutomationElement>,
}

impl Recorrido<'_> {
    fn agotado(&self) -> bool {
        self.crudos >= MAX_NODOS || Instant::now() >= self.limite
    }

    fn visitar(&mut self, el: &IUIAutomationElement, profundidad: usize) {
        self.crudos += 1;
        if let Some(c) = candidato_de(el) {
            self.candidatos.push(c);
            self.elementos.push(el.clone());
        }
        if profundidad >= MAX_PROFUNDIDAD {
            return;
        }
        let mut hijo = unsafe { self.caminante.GetFirstChildElementBuildCache(el, self.cache) };
        while let Ok(h) = hijo {
            if self.agotado() {
                return;
            }
            self.visitar(&h, profundidad + 1);
            if self.agotado() {
                return;
            }
            hijo = unsafe { self.caminante.GetNextSiblingElementBuildCache(&h, self.cache) };
        }
    }
}

fn titulo_de(hwnd: HWND) -> String {
    let mut buf = [0u16; 512];
    let n = unsafe { GetWindowTextW(hwnd, &mut buf) };
    String::from_utf16_lossy(&buf[..n.max(0) as usize])
}

fn proceso_de(hwnd: HWND) -> String {
    unsafe {
        let mut pid = 0u32;
        GetWindowThreadProcessId(hwnd, Some(&mut pid as *mut u32));
        let Ok(h) = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, pid) else {
            return String::new();
        };
        let mut buf = [0u16; 1024];
        let mut largo = buf.len() as u32;
        let r = QueryFullProcessImageNameW(h, PROCESS_NAME_WIN32, PWSTR(buf.as_mut_ptr()), &mut largo);
        let _ = CloseHandle(h);
        if r.is_err() {
            return String::new();
        }
        let ruta = String::from_utf16_lossy(&buf[..largo as usize]);
        ruta.rsplit('\\').next().unwrap_or("").to_string()
    }
}

pub fn leer(auto: &IUIAutomation, hwnd: HWND, presupuesto: Duration) -> Result<LecturaCruda, String> {
    if hwnd.0.is_null() {
        return Err("sin_ventana".into());
    }
    let inicio = Instant::now();
    let cache = pedido_cache(auto)?;
    let raiz = unsafe { auto.ElementFromHandleBuildCache(hwnd, &cache) }.map_err(|_| "sin_ventana".to_string())?;
    let caminante = unsafe { auto.ControlViewWalker() }.map_err(|e| e.to_string())?;
    let rect_ventana = unsafe { raiz.CachedBoundingRectangle() }
        .map(rect_de)
        .map_err(|e| e.to_string())?;
    let mut rec = Recorrido {
        caminante: &caminante,
        cache: &cache,
        limite: inicio + presupuesto,
        crudos: 0,
        candidatos: Vec::new(),
        elementos: Vec::new(),
    };
    rec.visitar(&raiz, 0);
    Ok(LecturaCruda {
        titulo: titulo_de(hwnd),
        proceso: proceso_de(hwnd),
        rect_ventana,
        candidatos: rec.candidatos,
        elementos: rec.elementos,
        crudos: rec.crudos,
        ms: inicio.elapsed().as_millis(),
    })
}

fn escribir_diagnostico(app: &AppHandle) -> Result<(), String> {
    let auto = crear_automation()?;
    let hwnd = unsafe { GetForegroundWindow() };
    let v1 = leer(&auto, hwnd, Duration::from_millis(PRESUPUESTO_MS))?;
    let mut ctrl = filtrar_y_numerar(&v1.candidatos, v1.rect_ventana, TOPE_CONTROLES);
    let mut lineas = vec![format!(
        "vuelta 1: {} ms, {} crudos, {} controles",
        v1.ms, v1.crudos, ctrl.len()
    )];
    let mut lectura = v1;
    if necesita_reintento(ctrl.len()) {
        let v2 = leer(&auto, hwnd, Duration::from_millis(PRESUPUESTO_REINTENTO_MS))?;
        ctrl = filtrar_y_numerar(&v2.candidatos, v2.rect_ventana, TOPE_CONTROLES);
        lineas.push(format!(
            "vuelta 2: {} ms, {} crudos, {} controles",
            v2.ms, v2.crudos, ctrl.len()
        ));
        lectura = v2;
    }

    let mut monitores: Vec<(Rect, f64)> = Vec::new();
    for m in app.available_monitors().map_err(|e| e.to_string())? {
        let p = m.position();
        let s = m.size();
        monitores.push((Rect { x: p.x, y: p.y, ancho: s.width, alto: s.height }, m.scale_factor()));
    }
    let r = lectura.rect_ventana;
    let centro = Ancla {
        x: r.x + (r.ancho / 2) as i32,
        y: r.y + (r.alto / 2) as i32,
    };
    let rects: Vec<Rect> = monitores.iter().map(|(r, _)| *r).collect();
    let (mon, escala) = monitor_de(centro, &rects)
        .map(|i| monitores[i])
        .unwrap_or((r, 1.0));

    let mut salida = format!(
        "ventana: {} | proceso: {} | monitor: {},{} {}x{} | escala: {}\n",
        lectura.titulo, lectura.proceso, mon.x, mon.y, mon.ancho, mon.alto, escala
    );
    for l in lineas {
        salida.push_str(&l);
        salida.push('\n');
    }
    for (c, i) in &ctrl {
        let f = lectura.candidatos[*i].rect;
        let logico = a_overlay(f, mon, escala)
            .map(|l| format!("{},{},{},{}", l.x, l.y, l.ancho, l.alto))
            .unwrap_or_else(|| "fuera del monitor".into());
        salida.push_str(&format!(
            "{} | {} | {} | físico {},{},{},{} | lógico {}\n",
            c.n,
            serde_json::to_value(c.tipo).ok().and_then(|v| v.as_str().map(String::from)).unwrap_or_default(),
            c.nombre, f.x, f.y, f.ancho, f.alto, logico
        ));
    }

    let dir = app.path().app_config_dir().map_err(|e| e.to_string())?;
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    std::fs::write(dir.join("nudo-diagnostico.txt"), salida).map_err(|e| e.to_string())
}

pub fn diagnostico_en_hilo(app: AppHandle) {
    std::thread::spawn(move || {
        std::thread::sleep(Duration::from_secs(3));
        if let Err(e) = escribir_diagnostico(&app) {
            if let Ok(dir) = app.path().app_config_dir() {
                let _ = std::fs::write(dir.join("nudo-diagnostico.txt"), format!("error: {e}\n"));
            }
        }
    });
}

// ---- Ventana al frente que no es de Colmena ----

static VIGIA: OnceLock<Arc<AtomicIsize>> = OnceLock::new();
static APP: OnceLock<AppHandle> = OnceLock::new();
static EFIMERA: AtomicIsize = AtomicIsize::new(0);

fn clase_de(hwnd: HWND) -> String {
    let mut buf = [0u16; 256];
    let n = unsafe { GetClassNameW(hwnd, &mut buf) };
    String::from_utf16_lossy(&buf[..n.max(0) as usize])
}

fn es_ajena(hwnd: HWND) -> bool {
    if hwnd.0.is_null() {
        return false;
    }
    let mut pid = 0u32;
    unsafe { GetWindowThreadProcessId(hwnd, Some(&mut pid as *mut u32)) };
    pid != 0 && pid != std::process::id() && !ventana_de_sistema(&clase_de(hwnd))
}

fn pid_de(hwnd: HWND) -> u32 {
    let mut pid = 0u32;
    unsafe { GetWindowThreadProcessId(hwnd, Some(&mut pid as *mut u32)) };
    pid
}

/// Menú o popup de la ventana guardada (el ⋮ de Chrome): no reemplaza a la ventana de Ando.
fn es_efimera_de_la_guardada(hwnd: HWND) -> bool {
    let Some(g) = guardada() else {
        return false;
    };
    let clase = clase_de(hwnd);
    es_efimera(&datos_de(hwnd, &clase), Some(g))
}

fn guardada() -> Option<Guardada> {
    let guardada = hwnd_de(VIGIA.get()?);
    if guardada.0.is_null() {
        return None;
    }
    Some(Guardada { hwnd: guardada.0 as isize, pid: pid_de(guardada) })
}

fn datos_de<'a>(hwnd: HWND, clase: &'a str) -> VentanaNueva<'a> {
    let (ex, estilo) = unsafe { (GetWindowLongPtrW(hwnd, GWL_EXSTYLE) as u32, GetWindowLongPtrW(hwnd, GWL_STYLE) as u32) };
    let dueno_raiz = unsafe { GetAncestor(hwnd, GA_ROOTOWNER) };
    VentanaNueva {
        clase,
        pid: pid_de(hwnd),
        dueno_raiz: dueno_raiz.0 as isize,
        tiene_dueno: unsafe { GetWindow(hwnd, GW_OWNER) }.is_ok_and(|d| !d.0.is_null()),
        ex_toolwindow: ex & WS_EX_TOOLWINDOW.0 != 0,
        ex_noactivate: ex & WS_EX_NOACTIVATE.0 != 0,
        tiene_caption: estilo & WS_CAPTION.0 == WS_CAPTION.0,
    }
}

unsafe extern "system" fn juntar_ventana(hwnd: HWND, lparam: LPARAM) -> BOOL {
    let lista = unsafe { &mut *(lparam.0 as *mut Vec<HWND>) };
    lista.push(hwnd);
    BOOL(1)
}

/// Menús y popups abiertos de la ventana guardada, recorriendo las ventanas de primer nivel:
/// el menú ⋮ de Chrome no pasa a estar al frente y su aviso de menú puede llegar con otra ventana.
fn popups_abiertos(g: Guardada) -> Vec<Rect> {
    let mut hwnds: Vec<HWND> = Vec::new();
    unsafe {
        let _ = EnumWindows(Some(juntar_ventana), LPARAM(&mut hwnds as *mut Vec<HWND> as isize));
    }
    // Primero lo barato (visible, proceso o dueño): la clase y los estilos solo de las que pueden ser.
    let mut crudas: Vec<(HWND, Rect, String)> = Vec::new();
    for hwnd in hwnds {
        if !unsafe { IsWindowVisible(hwnd).as_bool() } {
            continue;
        }
        let dueno = unsafe { GetAncestor(hwnd, GA_ROOTOWNER) };
        if pid_de(hwnd) != g.pid && dueno.0 as isize != g.hwnd {
            continue;
        }
        let mut r = RECT::default();
        if unsafe { GetWindowRect(hwnd, &mut r) }.is_err() {
            continue;
        }
        crudas.push((hwnd, rect_de(r), clase_de(hwnd)));
    }
    let lista: Vec<VentanaListada> = crudas
        .iter()
        .map(|(hwnd, rect, clase)| VentanaListada { hwnd: hwnd.0 as isize, visible: true, rect: *rect, datos: datos_de(*hwnd, clase) })
        .collect();
    popups_de_la_guardada(&lista, g)
}

fn reafirmar_arriba() {
    #[cfg(windows)]
    if let Some(app) = APP.get() {
        crate::ventanas::reafirmar_arriba(app);
    }
}

fn ventana_usable(hwnd: HWND) -> bool {
    es_ajena(hwnd)
        && unsafe { IsWindow(Some(hwnd)).as_bool() && IsWindowVisible(hwnd).as_bool() && !IsIconic(hwnd).as_bool() }
}

fn hwnd_de(vigia: &AtomicIsize) -> HWND {
    HWND(vigia.load(Ordering::SeqCst) as *mut core::ffi::c_void)
}

unsafe extern "system" fn al_cambiar_frente(
    _hook: HWINEVENTHOOK,
    _evento: u32,
    hwnd: HWND,
    id_objeto: i32,
    _id_hijo: i32,
    _hilo: u32,
    _ms: u32,
) {
    // 0 = OBJID_WINDOW: la ventana en sí, no un objeto dentro de ella.
    if id_objeto != 0 || !es_ajena(hwnd) {
        return;
    }
    // Un menú o popup puede haberse puesto sobre el notch y el globo.
    reafirmar_arriba();
    if es_efimera_de_la_guardada(hwnd) {
        EFIMERA.store(hwnd.0 as isize, Ordering::SeqCst);
        return;
    }
    if let Some(v) = VIGIA.get() {
        v.store(hwnd.0 as isize, Ordering::SeqCst);
    }
}

unsafe extern "system" fn al_abrir_menu(
    _hook: HWINEVENTHOOK,
    _evento: u32,
    hwnd: HWND,
    _id_objeto: i32,
    _id_hijo: i32,
    _hilo: u32,
    _ms: u32,
) {
    reafirmar_arriba();
    if hwnd.0.is_null() {
        return;
    }
    let es_raiz = unsafe { GetAncestor(hwnd, GA_ROOT) } == hwnd;
    if (es_raiz && es_efimera_de_la_guardada(hwnd)) || clase_de(hwnd) == "#32768" {
        EFIMERA.store(hwnd.0 as isize, Ordering::SeqCst);
    }
}

/// Rect físico (GetWindowRect) del último menú o popup efímero visto por los avisos, si sigue abierto.
fn rect_del_aviso() -> Option<Rect> {
    let hwnd = HWND(EFIMERA.load(Ordering::SeqCst) as *mut core::ffi::c_void);
    if hwnd.0.is_null() || !unsafe { IsWindow(Some(hwnd)).as_bool() && IsWindowVisible(hwnd).as_bool() } {
        return None;
    }
    let mut r = RECT::default();
    if unsafe { GetWindowRect(hwnd, &mut r) }.is_err() || r.right <= r.left || r.bottom <= r.top {
        return None;
    }
    Some(rect_de(r))
}

/// Rects físicos de los menús o popups abiertos de la ventana guardada (los listados y el último aviso).
pub(super) fn rects_efimeros() -> Vec<Rect> {
    let mut rects = guardada().map(popups_abiertos).unwrap_or_default();
    if let Some(r) = rect_del_aviso() {
        if !rects.contains(&r) {
            rects.push(r);
        }
    }
    rects
}

pub(super) fn arrancar_vigia(vigia: Arc<AtomicIsize>, app: AppHandle) {
    if VIGIA.set(vigia).is_err() {
        return;
    }
    let _ = APP.set(app);
    let _ = std::thread::Builder::new().name("nudo-frente".into()).spawn(|| unsafe {
        let actual = GetForegroundWindow();
        if es_ajena(actual) {
            if let Some(v) = VIGIA.get() {
                v.store(actual.0 as isize, Ordering::SeqCst);
            }
        }
        // Aviso de cambio de ventana al frente (no es un gancho de teclado ni de mouse).
        let hook = SetWinEventHook(
            EVENT_SYSTEM_FOREGROUND,
            EVENT_SYSTEM_FOREGROUND,
            None,
            Some(al_cambiar_frente),
            0,
            0,
            WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS,
        );
        if hook.is_invalid() {
            eprintln!("nudo: no pude seguir la ventana al frente");
            return;
        }
        // Un menú que se abre no siempre cambia la ventana al frente: avisa aparte.
        let menu = SetWinEventHook(
            EVENT_SYSTEM_MENUPOPUPSTART,
            EVENT_SYSTEM_MENUPOPUPSTART,
            None,
            Some(al_abrir_menu),
            0,
            0,
            WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS,
        );
        if menu.is_invalid() {
            eprintln!("nudo: no pude seguir los menús abiertos");
        }
        let mut msg = MSG::default();
        while GetMessageW(&mut msg, None, 0, 0).0 > 0 {
            let _ = TranslateMessage(&msg);
            DispatchMessageW(&msg);
        }
    });
}

pub(super) fn rect_ventana(vigia: &AtomicIsize) -> Option<Rect> {
    let hwnd = hwnd_de(vigia);
    if !ventana_usable(hwnd) {
        return None;
    }
    let mut r = RECT::default();
    unsafe { GetWindowRect(hwnd, &mut r) }.ok()?;
    Some(rect_de(r))
}

/// El rect visible sale de DWM (sin el borde invisible de la sombra); si DWM falla, `GetWindowRect`.
pub(super) fn ventana_visible(vigia: &AtomicIsize) -> Option<(isize, Rect)> {
    let hwnd = hwnd_de(vigia);
    if !ventana_usable(hwnd) {
        return None;
    }
    let mut r = RECT::default();
    let dwm = unsafe {
        DwmGetWindowAttribute(
            hwnd,
            DWMWA_EXTENDED_FRAME_BOUNDS,
            &mut r as *mut RECT as *mut core::ffi::c_void,
            std::mem::size_of::<RECT>() as u32,
        )
    };
    if dwm.is_err() {
        r = RECT::default();
        unsafe { GetWindowRect(hwnd, &mut r) }.ok()?;
    }
    let rect = rect_de(r);
    if rect.ancho == 0 || rect.alto == 0 {
        return None;
    }
    Some((hwnd.0 as isize, rect))
}

// ---- Hilo COM dueño de la foto ----

struct Foto {
    id: u64,
    creada_ms: u64,
    elementos: Vec<IUIAutomationElement>,
}

type Leida = (String, String, Rect, Vec<ControlListado>, Vec<IUIAutomationElement>);

fn leer_foto(auto: &IUIAutomation, vigia: &AtomicIsize, permitir_vacia: bool) -> Result<Leida, String> {
    let hwnd = hwnd_de(vigia);
    if !ventana_usable(hwnd) {
        return Err(ERR_SIN_VENTANA.into());
    }
    let mut lectura = leer(auto, hwnd, Duration::from_millis(PRESUPUESTO_MS)).map_err(|e| codigo_de_error(&e))?;
    let mut ctrl = filtrar_y_numerar(&lectura.candidatos, lectura.rect_ventana, TOPE_CONTROLES);
    if necesita_reintento(ctrl.len()) {
        let otra = leer(auto, hwnd, Duration::from_millis(PRESUPUESTO_REINTENTO_MS)).map_err(|e| codigo_de_error(&e))?;
        let ctrl2 = filtrar_y_numerar(&otra.candidatos, otra.rect_ventana, TOPE_CONTROLES);
        if ctrl2.len() >= ctrl.len() {
            lectura = otra;
            ctrl = ctrl2;
        }
    }
    if ctrl.is_empty() && !permitir_vacia {
        return Err(ERR_SIN_CONTROLES.into());
    }
    let elementos = ctrl.iter().map(|(_, i)| lectura.elementos[*i].clone()).collect();
    let controles = ctrl.into_iter().map(|(c, _)| c).collect();
    Ok((lectura.titulo, lectura.proceso, lectura.rect_ventana, controles, elementos))
}

fn elemento(foto: Option<&Foto>, id: u64, idx: usize) -> Result<&IUIAutomationElement, String> {
    let f = foto.filter(|f| f.id == id).ok_or_else(|| ERR_FOTO_VIEJA.to_string())?;
    f.elementos.get(idx).ok_or_else(|| ERR_SIN_CONTROL.to_string())
}

fn posicion(foto: Option<&Foto>, id: u64, idx: usize, ahora_ms: Option<u64>) -> Result<Rect, String> {
    if let (Some(f), Some(ahora)) = (foto, ahora_ms) {
        if f.id == id && !foto_vigente(f.creada_ms, ahora) {
            return Err(ERR_FOTO_VIEJA.into());
        }
    }
    let el = elemento(foto, id, idx)?;
    let r = unsafe { el.CurrentBoundingRectangle() }.map_err(|_| ERR_FOTO_VIEJA.to_string())?;
    let fuera = unsafe { el.CurrentIsOffscreen() }.map(|b| b.as_bool()).unwrap_or(true);
    let r = rect_de(r);
    if !rect_utilizable(r, fuera) {
        return Err(ERR_FOTO_VIEJA.into());
    }
    Ok(r)
}

fn avisar(aviso: &Mutex<Option<Sender<String>>>) {
    if let Ok(mut g) = aviso.lock() {
        if let Some(tx) = g.take() {
            let _ = tx.send("usado".into());
        }
    }
}

#[implement(IUIAutomationEventHandler)]
struct AlInvocar {
    aviso: Arc<Mutex<Option<Sender<String>>>>,
}

impl IUIAutomationEventHandler_Impl for AlInvocar_Impl {
    fn HandleAutomationEvent(&self, _sender: Ref<IUIAutomationElement>, _evento: UIA_EVENT_ID) -> windows::core::Result<()> {
        avisar(&self.aviso);
        Ok(())
    }
}

#[implement(IUIAutomationFocusChangedEventHandler)]
struct AlEnfocar {
    aviso: Arc<Mutex<Option<Sender<String>>>>,
    auto: IUIAutomation,
    objetivo: IUIAutomationElement,
}

impl IUIAutomationFocusChangedEventHandler_Impl for AlEnfocar_Impl {
    fn HandleFocusChangedEvent(&self, sender: Ref<IUIAutomationElement>) -> windows::core::Result<()> {
        if let Some(el) = sender.as_ref() {
            if unsafe { self.auto.CompareElements(el, &self.objetivo) }.map(|b| b.as_bool()).unwrap_or(false) {
                avisar(&self.aviso);
            }
        }
        Ok(())
    }
}

/// Un botón que abre un menú (el ⋮ de Chrome) no se "invoca": pasa a expandido.
#[implement(IUIAutomationPropertyChangedEventHandler)]
struct AlExpandir {
    aviso: Arc<Mutex<Option<Sender<String>>>>,
}

impl IUIAutomationPropertyChangedEventHandler_Impl for AlExpandir_Impl {
    fn HandlePropertyChangedEvent(
        &self,
        _sender: Ref<IUIAutomationElement>,
        propiedad: UIA_PROPERTY_ID,
        valor: &VARIANT,
    ) -> windows::core::Result<()> {
        if propiedad == UIA_ExpandCollapseExpandCollapseStatePropertyId
            && i32::try_from(valor).is_ok_and(cuenta_como_expandido)
        {
            avisar(&self.aviso);
        }
        Ok(())
    }
}

fn vigilar(auto: &IUIAutomation, el: &IUIAutomationElement, usado: Sender<String>) {
    let aviso = Arc::new(Mutex::new(Some(usado)));
    let invocado: IUIAutomationEventHandler = AlInvocar { aviso: Arc::clone(&aviso) }.into();
    let expandido: IUIAutomationPropertyChangedEventHandler = AlExpandir { aviso: Arc::clone(&aviso) }.into();
    let foco: IUIAutomationFocusChangedEventHandler =
        AlEnfocar { aviso, auto: auto.clone(), objetivo: el.clone() }.into();
    unsafe {
        let _ = auto.AddAutomationEventHandler(
            UIA_Invoke_InvokedEventId,
            el,
            TreeScope_Element,
            None::<&IUIAutomationCacheRequest>,
            &invocado,
        );
        let _ = auto.AddPropertyChangedEventHandlerNativeArray(
            el,
            TreeScope_Element,
            None::<&IUIAutomationCacheRequest>,
            &expandido,
            &[UIA_ExpandCollapseExpandCollapseStatePropertyId],
        );
        let _ = auto.AddFocusChangedEventHandler(None::<&IUIAutomationCacheRequest>, &foco);
    }
}

fn fallar(p: PedidoUia) {
    match p {
        PedidoUia::Leer(r) | PedidoUia::LeerMostrar(r) => {
            let _ = r.send(Err(ERR_FALLO_PC.into()));
        }
        PedidoUia::Rect { resp, .. } | PedidoUia::Seguir { resp, .. } => {
            let _ = resp.send(Err(ERR_FALLO_PC.into()));
        }
        PedidoUia::Vigilar { .. } | PedidoUia::Soltar => {}
    }
}

pub(super) fn bucle(rx: Receiver<PedidoUia>, vigia: Arc<AtomicIsize>) {
    let auto = match crear_automation() {
        Ok(a) => a,
        Err(e) => {
            eprintln!("nudo: UI Automation no arrancó: {e}");
            for p in rx {
                fallar(p);
            }
            return;
        }
    };
    let base = Instant::now();
    let ahora_ms = || base.elapsed().as_millis() as u64;
    // Ids que no se repiten entre arranques: una foto de la corrida anterior nunca coincide.
    let mut proximo_id = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(1);
    let mut foto: Option<Foto> = None;

    for p in rx {
        let permitir_vacia = matches!(p, PedidoUia::LeerMostrar(_));
        match p {
            PedidoUia::Leer(resp) | PedidoUia::LeerMostrar(resp) => {
                let r = leer_foto(&auto, &vigia, permitir_vacia).map(|(titulo, proceso, ventana, controles, elementos)| {
                    proximo_id += 1;
                    foto = Some(Foto { id: proximo_id, creada_ms: ahora_ms(), elementos });
                    Lectura { foto: proximo_id, titulo, proceso, ventana, controles }
                });
                let _ = resp.send(r);
            }
            PedidoUia::Rect { foto: id, idx, resp } => {
                let _ = resp.send(posicion(foto.as_ref(), id, idx, Some(ahora_ms())));
            }
            PedidoUia::Seguir { foto: id, idx, resp } => {
                let _ = resp.send(posicion(foto.as_ref(), id, idx, None));
            }
            PedidoUia::Vigilar { foto: id, idx, usado } => {
                let _ = unsafe { auto.RemoveAllEventHandlers() };
                if let Ok(el) = elemento(foto.as_ref(), id, idx) {
                    vigilar(&auto, el, usado);
                }
            }
            PedidoUia::Soltar => {
                let _ = unsafe { auto.RemoveAllEventHandlers() };
            }
        }
    }
}
