use std::sync::atomic::Ordering;
use std::sync::mpsc::{Receiver, RecvTimeoutError, Sender};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use colmena_nucleo::posicion::Rect;
use colmena_nucleo::reunion::cajita::{es_acoplada, Accion, Escondedor, MOTIVO_ACOPLADA, MOTIVO_ESCONDIDA};
use colmena_nucleo::reunion::dedup::{contar_repetidas, Deduplicador};
use colmena_nucleo::reunion::tanda::Tanda;
use colmena_nucleo::reunion::subtitulos;
use colmena_nucleo::reunion::{espera, Espera, ESTADO_APAGADO, ESTADO_ESCUCHANDO, ESTADO_PAUSADO, ESTADO_SIN_SUBTITULOS};
use tauri::{AppHandle, Emitter, Manager};
use windows::core::{implement, w, Ref, BSTR, PWSTR};
use windows::Win32::System::Variant::VARIANT;
use windows::Win32::Foundation::{CloseHandle, HWND, LPARAM, RECT};
use windows::Win32::Graphics::Gdi::{GetMonitorInfoW, MonitorFromWindow, MONITORINFO, MONITOR_DEFAULTTONEAREST};
use windows::Win32::System::Com::{CoCreateInstance, CoInitializeEx, CLSCTX_INPROC_SERVER, COINIT_MULTITHREADED};
use windows::Win32::System::SystemInformation::GetLocalTime;
use windows::Win32::System::Threading::{
    OpenProcess, QueryFullProcessImageNameW, PROCESS_NAME_WIN32, PROCESS_QUERY_LIMITED_INFORMATION,
};
use windows::Win32::UI::Accessibility::{
    CUIAutomation, IUIAutomation, IUIAutomationCacheRequest, IUIAutomationElement,
    IUIAutomationEventHandler, IUIAutomationEventHandler_Impl, IUIAutomationPropertyChangedEventHandler,
    IUIAutomationPropertyChangedEventHandler_Impl, TreeScope_Descendants, TreeScope_Element,
    UIA_AutomationIdPropertyId, UIA_ControlTypePropertyId, UIA_EVENT_ID, UIA_E_ELEMENTNOTAVAILABLE,
    UIA_NamePropertyId, UIA_PROPERTY_ID, UIA_TextControlTypeId, UIA_Text_TextChangedEventId,
};
use windows::Win32::UI::WindowsAndMessaging::{
    EnumWindows, FindWindowW, GetClassNameW, GetWindowLongPtrW, GetWindowRect, GetWindowThreadProcessId, IsWindow,
    IsWindowVisible, PostMessageW, SetWindowLongPtrW, ShowWindow, GWL_EXSTYLE, SW_RESTORE, SW_SHOWMINNOACTIVE, WM_CLOSE,
    WS_EX_TOOLWINDOW,
};

use super::{Fuente, Mensaje, PedidoLector};
use crate::Estado;

const ESPERA_TICK: Duration = Duration::from_millis(1_000);
const SIN_EVENTOS_MS: u64 = 5_000;
const SONDEO_MS: u64 = 1_000;
const REBUSCAR_MS: u64 = 5_000; // también cada cuánto se revisa que la ventana siga viva
const DIAG_MS: u64 = 60_000;
const CRUDOS_MAX: usize = 40;
const ID_CAJITA: &str = "CaptionsTextBlock";

// ---- Búsqueda de la cajita de texto de Subtítulos en vivo ----

fn clase_de(hwnd: HWND) -> String {
    let mut buf = [0u16; 256];
    let n = unsafe { GetClassNameW(hwnd, &mut buf) };
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

unsafe extern "system" fn juntar_ventana(hwnd: HWND, lparam: LPARAM) -> windows::core::BOOL {
    let lista = unsafe { &mut *(lparam.0 as *mut Vec<HWND>) };
    if unsafe { IsWindowVisible(hwnd).as_bool() } && proceso_de(hwnd).eq_ignore_ascii_case("LiveCaptions.exe") {
        lista.push(hwnd);
    }
    true.into()
}

fn ventanas_candidatas() -> Vec<HWND> {
    let mut v = Vec::new();
    if let Ok(h) = unsafe { FindWindowW(w!("LiveCaptionsDesktopWindow"), None) } {
        if !h.0.is_null() {
            v.push(h);
        }
    }
    let mut de_proceso: Vec<HWND> = Vec::new();
    let _ = unsafe { EnumWindows(Some(juntar_ventana), LPARAM(&mut de_proceso as *mut Vec<HWND> as isize)) };
    for h in de_proceso {
        if !v.contains(&h) {
            v.push(h);
        }
    }
    v
}

// ---- Esconder la cajita para que no se vea al compartir pantalla ----

fn a_rect(r: RECT) -> Rect {
    Rect {
        x: r.left,
        y: r.top,
        ancho: (r.right - r.left).max(0) as u32,
        alto: (r.bottom - r.top).max(0) as u32,
    }
}

/// La ventana, el monitor donde está (no el principal: puede estar en otro) y su área de trabajo.
fn rect_y_monitor(hwnd: HWND) -> Option<(Rect, Rect, Rect)> {
    let mut r = RECT::default();
    unsafe { GetWindowRect(hwnd, &mut r) }.ok()?;
    let mon = unsafe { MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST) };
    let mut info = MONITORINFO { cbSize: std::mem::size_of::<MONITORINFO>() as u32, ..Default::default() };
    if !unsafe { GetMonitorInfoW(mon, &mut info) }.as_bool() {
        return None;
    }
    Some((a_rect(r), a_rect(info.rcMonitor), a_rect(info.rcWork)))
}

fn estilo_ex(hwnd: HWND) -> isize {
    unsafe { GetWindowLongPtrW(hwnd, GWL_EXSTYLE) }
}

fn tiene_toolwindow(hwnd: HWND) -> bool {
    estilo_ex(hwnd) & WS_EX_TOOLWINDOW.0 as isize != 0
}

/// Fuera de la barra de tareas y de Alt+Tab, minimizada sin robar el foco. UIA la sigue leyendo.
fn esconder(hwnd: HWND) {
    unsafe {
        SetWindowLongPtrW(hwnd, GWL_EXSTYLE, estilo_ex(hwnd) | WS_EX_TOOLWINDOW.0 as isize);
        let _ = ShowWindow(hwnd, SW_SHOWMINNOACTIVE);
    }
}

fn restaurar(hwnd: HWND) {
    unsafe {
        SetWindowLongPtrW(hwnd, GWL_EXSTYLE, estilo_ex(hwnd) & !(WS_EX_TOOLWINDOW.0 as isize));
        let _ = ShowWindow(hwnd, SW_RESTORE);
    }
}

/// Vuelve a mostrar las cajitas que escondió Colmena (al terminar o tras una caída).
fn restaurar_escondidas() {
    for h in ventanas_candidatas() {
        if tiene_toolwindow(h) {
            restaurar(h);
        }
    }
}

// ---- Abrir y cerrar los Subtítulos en vivo ----

fn ruta_subtitulos() -> Option<std::path::PathBuf> {
    let raiz = std::env::var_os("SystemRoot").or_else(|| std::env::var_os("windir"))?;
    Some(std::path::PathBuf::from(raiz).join("System32").join("LiveCaptions.exe"))
}

/// Lanza `LiveCaptions.exe`; `false` si no se pudo (la reunión sigue y el lector avisa "sin subtítulos").
fn abrir_subtitulos() -> bool {
    let Some(ruta) = ruta_subtitulos() else {
        eprintln!("reunión: no pude ubicar la carpeta de Windows para abrir los Subtítulos en vivo");
        return false;
    };
    match std::process::Command::new(ruta).spawn() {
        Ok(_) => true,
        Err(e) => {
            eprintln!("reunión: no pude abrir los Subtítulos en vivo: {e}");
            false
        }
    }
}

/// Pide el cierre normal de la ventana (WM_CLOSE), sin matar el proceso.
fn cerrar_subtitulos() {
    for h in ventanas_candidatas() {
        let _ = unsafe { PostMessageW(Some(h), WM_CLOSE, Default::default(), Default::default()) };
    }
}

fn area(el: &IUIAutomationElement) -> i64 {
    unsafe { el.CurrentBoundingRectangle() }
        .map(|r| (r.right - r.left).max(0) as i64 * (r.bottom - r.top).max(0) as i64)
        .unwrap_or(0)
}

fn elemento_de(auto: &IUIAutomation, hwnd: HWND) -> Option<(IUIAutomationElement, bool)> {
    unsafe {
        let raiz = auto.ElementFromHandle(hwnd).ok()?;
        let por_id = auto
            .CreatePropertyCondition(UIA_AutomationIdPropertyId, &VARIANT::from(BSTR::from(ID_CAJITA)))
            .ok()?;
        if let Ok(e) = raiz.FindFirst(TreeScope_Descendants, &por_id) {
            return Some((e, true));
        }
        let textos = auto
            .CreatePropertyCondition(UIA_ControlTypePropertyId, &VARIANT::from(UIA_TextControlTypeId.0))
            .ok()?;
        let todos = raiz.FindAll(TreeScope_Descendants, &textos).ok()?;
        (0..todos.Length().ok()?)
            .filter_map(|i| todos.GetElement(i).ok())
            .max_by_key(area)
            .map(|e| (e, false))
    }
}

pub(super) fn buscar_cajita(auto: &IUIAutomation) -> Option<(HWND, IUIAutomationElement, bool)> {
    ventanas_candidatas()
        .into_iter()
        .find_map(|h| elemento_de(auto, h).map(|(e, por_id)| (h, e, por_id)))
}

fn leer_nombre(elem: &IUIAutomationElement) -> windows::core::Result<String> {
    unsafe { elem.CurrentName() }.map(|b| b.to_string())
}

pub(super) fn texto_visible(elem: &IUIAutomationElement) -> String {
    leer_nombre(elem).unwrap_or_default()
}

fn no_disponible(e: &windows::core::Error) -> bool {
    e.code().0 as u32 == UIA_E_ELEMENTNOTAVAILABLE
}

// ---- Avisos de UIA: solo reenvían el texto al hilo del lector ----

#[implement(IUIAutomationPropertyChangedEventHandler)]
struct AlCambiarNombre {
    tx: Sender<Mensaje>,
}

impl IUIAutomationPropertyChangedEventHandler_Impl for AlCambiarNombre_Impl {
    fn HandlePropertyChangedEvent(
        &self,
        sender: Ref<IUIAutomationElement>,
        _id: UIA_PROPERTY_ID,
        _nuevo: &VARIANT,
    ) -> windows::core::Result<()> {
        if let Some(el) = sender.as_ref() {
            let _ = self.tx.send(Mensaje::Evento(Fuente::Nombre, texto_visible(el)));
        }
        Ok(())
    }
}

#[implement(IUIAutomationEventHandler)]
struct AlCambiarTexto {
    tx: Sender<Mensaje>,
}

impl IUIAutomationEventHandler_Impl for AlCambiarTexto_Impl {
    fn HandleAutomationEvent(&self, sender: Ref<IUIAutomationElement>, _evento: UIA_EVENT_ID) -> windows::core::Result<()> {
        if let Some(el) = sender.as_ref() {
            let _ = self.tx.send(Mensaje::Evento(Fuente::TextoCambiado, texto_visible(el)));
        }
        Ok(())
    }
}

// ---- Diagnóstico de 60 s ----

struct Diagnostico {
    fin_ms: u64,
    eventos_nombre: u32,
    eventos_texto: u32,
    sondeo_desde_s: Option<u64>,
    crudos: Vec<(u64, String)>,
    tandas: Vec<(String, String)>,
    ventana: String,
    elemento: String,
}

fn hora_local() -> String {
    let t = unsafe { GetLocalTime() };
    format!("{:02}:{:02}:{:02}", t.wHour, t.wMinute, t.wSecond)
}

fn describir(hwnd: HWND, el: &IUIAutomationElement) -> (String, String) {
    let ventana = format!("encontrada clase={} proceso={}", clase_de(hwnd), proceso_de(hwnd));
    let id = unsafe { el.CurrentAutomationId() }.map(|b| b.to_string()).unwrap_or_default();
    let tipo = unsafe { el.CurrentControlType() }.map(|t| t.0).unwrap_or(0);
    let via = if id == ID_CAJITA { ID_CAJITA } else { "texto mayor" };
    (ventana, format!("{via} tipo={tipo}"))
}

impl Diagnostico {
    fn nuevo(ahora_ms: u64) -> Self {
        Self {
            fin_ms: ahora_ms + DIAG_MS,
            eventos_nombre: 0,
            eventos_texto: 0,
            sondeo_desde_s: None,
            crudos: Vec::new(),
            tandas: Vec::new(),
            ventana: "no".into(),
            elemento: "no".into(),
        }
    }

    fn escribir(&self, app: &AppHandle) -> Result<(), String> {
        let frases: Vec<String> = self.tandas.iter().map(|(_, t)| t.clone()).collect();
        let caracteres: usize = frases.iter().map(|t| t.chars().count()).sum();
        let sondeo = self.sondeo_desde_s.map_or("no".to_string(), |s| format!("sí desde los {s} s"));
        let mut salida = format!(
            "ventana: {}\nelemento: {}\neventos: name={} textchanged={} | sondeo: {}\ntandas: {} | caracteres: {} | repetidas: {}\n--- texto deduplicado ---\n",
            self.ventana,
            self.elemento,
            self.eventos_nombre,
            self.eventos_texto,
            sondeo,
            frases.len(),
            caracteres,
            contar_repetidas(&frases),
        );
        for (hora, t) in &self.tandas {
            salida.push_str(&format!("[{hora}] {t}\n"));
        }
        let mut crudo = String::new();
        for (ms, t) in &self.crudos {
            crudo.push_str(&format!("{ms} ms | {t}\n"));
        }
        let dir = app.path().app_config_dir().map_err(|e| e.to_string())?;
        std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
        std::fs::write(dir.join("reunion-diagnostico.txt"), salida).map_err(|e| e.to_string())?;
        std::fs::write(dir.join("reunion-crudo.txt"), crudo).map_err(|e| e.to_string())
    }
}

// ---- El lector ----

struct Lector {
    app: AppHandle,
    tx: Sender<Mensaje>,
    auto: IUIAutomation,
    base: Instant,
    estado: &'static str,
    emitido: &'static str,
    cajita: Option<(HWND, IUIAutomationElement)>,
    /// La cajita se halló por su id; si no, es el "texto mayor" y se sigue buscando la real.
    cajita_por_id: bool,
    dedup: Deduplicador,
    tanda: Tanda,
    escuchando_desde_ms: u64,
    eventos: u32,
    ultimo_sondeo_ms: u64,
    sondeando: bool,
    ultima_busqueda_ms: u64,
    /// Cuándo Colmena lanzó los Subtítulos en esta reunión: hasta que Windows los muestre no es "Sin subtítulos".
    abiertos_en_ms: Option<u64>,
    ultimo_visible: String,
    diag: Option<Diagnostico>,
    escondedor: Escondedor,
}

impl Lector {
    fn ahora(&self) -> u64 {
        self.base.elapsed().as_millis() as u64
    }

    /// Lee la caja: en el modo normal (`estado` escuchando) o solo para el diagnóstico.
    fn activo(&self) -> bool {
        self.estado == ESTADO_ESCUCHANDO || self.estado == ESTADO_SIN_SUBTITULOS || self.diag.is_some()
    }

    fn conectar(&mut self) {
        let ahora = self.ahora();
        self.ultima_busqueda_ms = ahora;
        match buscar_cajita(&self.auto) {
            Some((h, el, por_id)) => {
                self.registrar(&el);
                if let Some(d) = self.diag.as_mut() {
                    (d.ventana, d.elemento) = describir(h, &el);
                }
                self.cajita = Some((h, el));
                self.cajita_por_id = por_id;
                if self.estado == ESTADO_ESCUCHANDO || self.estado == ESTADO_SIN_SUBTITULOS {
                    self.ocultar_cajita(h);
                }
                self.escuchando_desde_ms = ahora;
                self.eventos = 0;
                self.sondeando = false;
                if self.estado == ESTADO_SIN_SUBTITULOS {
                    self.estado = ESTADO_ESCUCHANDO;
                }
            }
            None => {
                if self.estado == ESTADO_ESCUCHANDO && !subtitulos::en_gracia(self.abiertos_en_ms, ahora) {
                    self.estado = ESTADO_SIN_SUBTITULOS;
                }
            }
        }
    }

    /// Una sola vez por reunión: si Ando la vuelve a abrir, se respeta.
    fn ocultar_cajita(&mut self, h: HWND) {
        let acoplada = rect_y_monitor(h).is_some_and(|(v, m, t)| es_acoplada(&v, &m, &t));
        match self.escondedor.ante(h.0 as isize, acoplada) {
            Accion::Esconder => {
                esconder(h);
                self.estado = ESTADO_ESCUCHANDO;
                self.sincronizar(Some(MOTIVO_ESCONDIDA));
            }
            Accion::Avisar => {
                self.estado = ESTADO_ESCUCHANDO;
                self.sincronizar(Some(MOTIVO_ACOPLADA));
            }
            Accion::Nada => {}
        }
    }

    fn registrar(&self, el: &IUIAutomationElement) {
        let nombre: IUIAutomationPropertyChangedEventHandler = AlCambiarNombre { tx: self.tx.clone() }.into();
        let texto: IUIAutomationEventHandler = AlCambiarTexto { tx: self.tx.clone() }.into();
        unsafe {
            let _ = self.auto.AddPropertyChangedEventHandlerNativeArray(
                el,
                TreeScope_Element,
                None::<&IUIAutomationCacheRequest>,
                &nombre,
                &[UIA_NamePropertyId],
            );
            let _ = self.auto.AddAutomationEventHandler(
                UIA_Text_TextChangedEventId,
                el,
                TreeScope_Element,
                None::<&IUIAutomationCacheRequest>,
                &texto,
            );
        }
    }

    fn soltar(&mut self) {
        let _ = unsafe { self.auto.RemoveAllEventHandlers() };
        self.cajita = None;
    }

    fn pedido(&mut self, p: PedidoLector) {
        let ahora = self.ahora();
        match p {
            PedidoLector::Escuchar => {
                let estado = self.app.state::<Estado>();
                let plan = subtitulos::al_empezar(
                    !ventanas_candidatas().is_empty(),
                    estado.reunion.subtitulos_de_colmena.load(Ordering::SeqCst),
                );
                let lanzados = plan.abrir && abrir_subtitulos();
                let marca = plan.marca && (!plan.abrir || lanzados);
                self.abiertos_en_ms = lanzados.then_some(ahora);
                estado.reunion.subtitulos_de_colmena.store(marca, Ordering::SeqCst);
                self.soltar();
                self.dedup = Deduplicador::default();
                self.tanda = Tanda::default();
                self.escondedor.olvidar();
                self.estado = ESTADO_ESCUCHANDO;
                self.conectar();
            }
            PedidoLector::Pausar => {
                if self.estado == ESTADO_ESCUCHANDO || self.estado == ESTADO_SIN_SUBTITULOS {
                    self.estado = ESTADO_PAUSADO;
                    self.soltar();
                }
            }
            PedidoLector::Seguir => {
                if self.estado == ESTADO_PAUSADO {
                    self.estado = ESTADO_ESCUCHANDO;
                    if self.cajita.is_none() {
                        self.conectar();
                    }
                }
            }
            PedidoLector::Terminar => {
                let abiertos = self.app.state::<Estado>().reunion.subtitulos_de_colmena.swap(false, Ordering::SeqCst);
                if subtitulos::al_terminar(abiertos) {
                    cerrar_subtitulos();
                } else {
                    restaurar_escondidas();
                }
                self.escondedor.olvidar();
                self.cerrar_lectura(ahora);
                self.estado = ESTADO_APAGADO;
                if self.diag.is_none() {
                    self.soltar();
                }
            }
            PedidoLector::Diagnostico => {
                self.diag = Some(Diagnostico::nuevo(ahora));
                if self.cajita.is_none() {
                    self.conectar();
                } else if let (Some(d), Some((h, el))) = (self.diag.as_mut(), self.cajita.as_ref()) {
                    (d.ventana, d.elemento) = describir(*h, el);
                }
            }
        }
    }

    /// Guarda el estado en la app y avisa al notch si cambió (o siempre que haya un motivo, como la bandeja).
    fn sincronizar(&mut self, motivo: Option<&'static str>) {
        if self.estado == self.emitido && motivo.is_none() {
            return;
        }
        self.emitido = self.estado;
        *self.app.state::<Estado>().reunion.lector.lock().unwrap() = self.estado;
        for destino in ["notch", "reunion"] {
            let _ = self.app.emit_to(
                destino,
                "reunion-lector",
                serde_json::json!({ "estado": self.estado, "motivo": motivo }),
            );
        }
    }

    fn cerrar_lectura(&mut self, ahora: u64) {
        if let Some(frase) = self.dedup.cerrar() {
            self.agregar_a_tanda(&frase, ahora);
        }
        if let Some(t) = self.tanda.vaciar() {
            self.salida(t);
        }
    }

    /// Texto crudo de la caja (de un aviso o del sondeo).
    fn visible(&mut self, texto: &str) {
        if !self.activo() || self.estado == ESTADO_PAUSADO {
            return;
        }
        let ahora = self.ahora();
        if texto != self.ultimo_visible {
            self.ultimo_visible = texto.to_string();
            if let Some(d) = self.diag.as_mut() {
                if d.crudos.len() < CRUDOS_MAX && !texto.trim().is_empty() {
                    d.crudos.push((ahora, texto.to_string()));
                }
            }
        }
        if let Some(frase) = self.dedup.observar(texto, ahora) {
            self.agregar_a_tanda(&frase, ahora);
        }
    }

    fn agregar_a_tanda(&mut self, frase: &str, ahora: u64) {
        for t in self.tanda.agregar(frase, ahora) {
            self.salida(t);
        }
    }

    /// Cada tanda va al notch mientras hay una reunión en curso y, si corre, al diagnóstico.
    fn salida(&mut self, tanda: String) {
        if self.estado != ESTADO_APAGADO {
            let ts = SystemTime::now().duration_since(UNIX_EPOCH).map_or(0, |d| d.as_millis() as u64);
            let _ = self.app.emit_to("notch", "reunion-texto", serde_json::json!({ "texto": tanda, "ts": ts }));
        }
        if let Some(d) = self.diag.as_mut() {
            d.tandas.push((hora_local(), tanda));
        }
    }

    fn evento(&mut self, fuente: Fuente, texto: &str) {
        if let Some(d) = self.diag.as_mut() {
            match fuente {
                Fuente::Nombre => d.eventos_nombre += 1,
                Fuente::TextoCambiado => d.eventos_texto += 1,
            }
        }
        self.eventos += 1;
        self.visible(texto);
    }

    fn tick(&mut self) {
        let ahora = self.ahora();
        if self.activo() && self.estado != ESTADO_PAUSADO {
            self.tick_lectura(ahora);
        }
        if self.diag.as_ref().is_some_and(|d| ahora >= d.fin_ms) {
            self.terminar_diagnostico(ahora);
        }
    }

    fn tick_lectura(&mut self, ahora: u64) {
        let Some((hwnd, el)) = self.cajita.clone() else {
            if ahora.saturating_sub(self.ultima_busqueda_ms) >= subtitulos::rebusca_ms(self.abiertos_en_ms, ahora) {
                self.conectar();
            }
            return;
        };
        if subtitulos::rebuscar_cajita(self.cajita_por_id, ahora, self.ultima_busqueda_ms, self.abiertos_en_ms) {
            self.ultima_busqueda_ms = ahora;
            if let Some((h, nuevo, true)) = buscar_cajita(&self.auto) {
                self.soltar();
                self.registrar(&nuevo);
                if let Some(d) = self.diag.as_mut() {
                    (d.ventana, d.elemento) = describir(h, &nuevo);
                }
                self.cajita = Some((h, nuevo));
                self.cajita_por_id = true;
                self.escuchando_desde_ms = ahora;
                self.eventos = 0;
                self.sondeando = false;
                return;
            }
        }
        if self.eventos == 0 && ahora.saturating_sub(self.escuchando_desde_ms) >= SIN_EVENTOS_MS {
            if !self.sondeando {
                self.sondeando = true;
                if let Some(d) = self.diag.as_mut() {
                    d.sondeo_desde_s = Some(ahora.saturating_sub(self.escuchando_desde_ms) / 1000);
                }
            }
            if ahora.saturating_sub(self.ultimo_sondeo_ms) >= SONDEO_MS {
                self.ultimo_sondeo_ms = ahora;
                match leer_nombre(&el) {
                    Ok(t) => self.visible(&t),
                    Err(e) if no_disponible(&e) => return self.perder_cajita(),
                    Err(_) => {}
                }
            }
        } else if ahora.saturating_sub(self.ultimo_sondeo_ms) >= REBUSCAR_MS {
            self.ultimo_sondeo_ms = ahora;
            if !unsafe { IsWindow(Some(hwnd)).as_bool() } {
                return self.perder_cajita();
            }
        }
        if let Some(frase) = self.dedup.tick(ahora) {
            self.agregar_a_tanda(&frase, ahora);
        }
        if let Some(t) = self.tanda.tick(ahora) {
            self.salida(t);
        }
    }

    fn perder_cajita(&mut self) {
        self.soltar();
        if self.estado == ESTADO_ESCUCHANDO {
            self.estado = ESTADO_SIN_SUBTITULOS;
        }
        self.ultima_busqueda_ms = self.ahora();
    }

    fn terminar_diagnostico(&mut self, ahora: u64) {
        self.cerrar_lectura(ahora);
        let Some(d) = self.diag.take() else { return };
        if let Err(e) = d.escribir(&self.app) {
            if let Ok(dir) = self.app.path().app_config_dir() {
                let _ = std::fs::write(dir.join("reunion-diagnostico.txt"), format!("error: {e}\n"));
            }
        }
        if self.estado != ESTADO_ESCUCHANDO {
            self.soltar();
        }
    }
}

pub(super) fn bucle(rx: Receiver<Mensaje>, tx: Sender<Mensaje>, app: AppHandle) {
    let auto = unsafe {
        // S_FALSE (ya iniciado) y RPC_E_CHANGED_MODE no impiden usar UIA en este hilo.
        let _ = CoInitializeEx(None, COINIT_MULTITHREADED);
        match CoCreateInstance::<_, IUIAutomation>(&CUIAutomation, None, CLSCTX_INPROC_SERVER) {
            Ok(a) => a,
            Err(e) => {
                eprintln!("reunión: UI Automation no arrancó: {e}");
                return;
            }
        }
    };
    let mut lector = Lector {
        app,
        tx,
        auto,
        base: Instant::now(),
        estado: ESTADO_APAGADO,
        emitido: ESTADO_APAGADO,
        cajita: None,
        cajita_por_id: false,
        dedup: Deduplicador::default(),
        tanda: Tanda::default(),
        escuchando_desde_ms: 0,
        eventos: 0,
        ultimo_sondeo_ms: 0,
        sondeando: false,
        ultima_busqueda_ms: 0,
        abiertos_en_ms: None,
        ultimo_visible: String::new(),
        diag: None,
        escondedor: Escondedor::default(),
    };
    // Recién arrancada no hay reunión: una cajita escondida quedó de una caída de Colmena.
    restaurar_escondidas();
    loop {
        let recibido = match espera(lector.estado, lector.diag.is_some()) {
            Espera::Bloquear => rx.recv().map_err(|_| RecvTimeoutError::Disconnected),
            Espera::ConTimeout => rx.recv_timeout(ESPERA_TICK),
        };
        match recibido {
            Ok(Mensaje::Pedido(p)) => lector.pedido(p),
            Ok(Mensaje::Pedir(s)) => {
                lector.pedido(s.pedido);
                lector.sincronizar(s.motivo);
                let _ = s.tx.send(lector.estado);
            }
            Ok(Mensaje::Evento(f, t)) => lector.evento(f, &t),
            Err(RecvTimeoutError::Timeout) => {}
            Err(RecvTimeoutError::Disconnected) => break,
        }
        lector.tick();
        lector.sincronizar(None);
    }
}
