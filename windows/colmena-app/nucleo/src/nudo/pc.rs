use crate::posicion::Rect;

use super::{
    ERR_APAGADO, ERR_EN_CURSO, ERR_FALLO_PC, ERR_FOTO_VIEJA, ERR_INVALIDO, ERR_OCUPADO,
    ERR_SIN_CONTROL, ERR_SIN_CONTROLES, ERR_SIN_PC, ERR_SIN_VENTANA, ERR_VENCIDO,
};

const CODIGOS: [&str; 11] = [
    ERR_APAGADO, ERR_SIN_PC, ERR_SIN_VENTANA, ERR_SIN_CONTROLES, ERR_FOTO_VIEJA, ERR_SIN_CONTROL,
    ERR_OCUPADO, ERR_EN_CURSO, ERR_VENCIDO, ERR_INVALIDO, ERR_FALLO_PC,
];

// Barra de tareas, escritorio, Inicio/búsqueda/bloqueo y Alt+Tab: nunca son "la ventana de Ando".
const CLASES_SISTEMA: [&str; 9] = [
    "Shell_TrayWnd",
    "Shell_SecondaryTrayWnd",
    "Progman",
    "WorkerW",
    "Windows.UI.Core.CoreWindow",
    "XamlExplorerHostIslandWindow",
    "MultitaskingViewFrame",
    "ForegroundStaging",
    "NotifyIconOverflowWindow",
];

pub fn texto_monitor(m: Rect) -> String {
    format!("{},{} {}x{}", m.x, m.y, m.ancho, m.alto)
}

fn solape(a: Rect, b: Rect) -> i64 {
    let x0 = i64::from(a.x).max(i64::from(b.x));
    let y0 = i64::from(a.y).max(i64::from(b.y));
    let x1 = (i64::from(a.x) + i64::from(a.ancho)).min(i64::from(b.x) + i64::from(b.ancho));
    let y1 = (i64::from(a.y) + i64::from(a.alto)).min(i64::from(b.y) + i64::from(b.alto));
    (x1 - x0).max(0) * (y1 - y0).max(0)
}

/// Monitor que contiene el centro del rect; si el centro cae afuera, el que más ve de él.
pub fn monitor_para(r: Rect, monitores: &[Rect]) -> Option<usize> {
    if r.ancho == 0 || r.alto == 0 {
        return None;
    }
    let centro = crate::posicion::Ancla {
        x: (i64::from(r.x) + i64::from(r.ancho) / 2) as i32,
        y: (i64::from(r.y) + i64::from(r.alto) / 2) as i32,
    };
    if let Some(i) = crate::posicion::monitor_de(centro, monitores) {
        return Some(i);
    }
    monitores
        .iter()
        .enumerate()
        .map(|(i, m)| (i, solape(r, *m)))
        .filter(|(_, a)| *a > 0)
        .max_by_key(|(_, a)| *a)
        .map(|(i, _)| i)
}

/// Índice del control `n` si `foto` es la foto actual (id, cantidad de controles).
pub fn indice_en_foto(actual: Option<(u64, usize)>, foto: u64, n: u32) -> Result<usize, String> {
    match actual {
        Some((id, cantidad)) if id == foto => super::orden::validar_n(n, cantidad),
        _ => Err(ERR_FOTO_VIEJA.into()),
    }
}

pub fn rect_utilizable(r: Rect, fuera_de_pantalla: bool) -> bool {
    !fuera_de_pantalla && r.ancho > 0 && r.alto > 0
}

pub fn codigo_de_error(e: &str) -> String {
    CODIGOS.iter().find(|c| **c == e).unwrap_or(&ERR_FALLO_PC).to_string()
}

pub fn ventana_de_sistema(clase: &str) -> bool {
    CLASES_SISTEMA.contains(&clase)
}

/// Ventana nueva al frente, con los datos que el sistema da de ella.
pub struct VentanaNueva<'a> {
    pub clase: &'a str,
    pub pid: u32,
    /// Ventana raíz de la cadena de dueños (ella misma si no tiene dueño).
    pub dueno_raiz: isize,
    pub tiene_dueno: bool,
    pub ex_toolwindow: bool,
    pub ex_noactivate: bool,
    pub tiene_caption: bool,
}

/// La ventana de Ando que la guía ya tiene guardada.
#[derive(Clone, Copy)]
pub struct Guardada {
    pub hwnd: isize,
    pub pid: u32,
}

/// Menús y popups de la propia ventana guardada (el ⋮ de Chrome): no son "la ventana de Ando",
/// se conserva la anterior para que la foto siga valiendo.
pub fn es_efimera(v: &VentanaNueva, g: Option<Guardada>) -> bool {
    let Some(g) = g else {
        return false;
    };
    let mismo_proceso = v.pid == g.pid;
    if v.clase == "#32768" {
        return mismo_proceso;
    }
    let forma_popup = v.ex_toolwindow || v.ex_noactivate || (v.tiene_dueno && !v.tiene_caption);
    let del_dueno = (v.tiene_dueno && v.dueno_raiz == g.hwnd) || mismo_proceso;
    forma_popup && del_dueno
}

/// Ventana de primer nivel tal como la lista el sistema (EnumWindows).
pub struct VentanaListada<'a> {
    pub hwnd: isize,
    pub visible: bool,
    /// Rect físico (GetWindowRect).
    pub rect: Rect,
    pub datos: VentanaNueva<'a>,
}

/// Rects de los menús y popups abiertos de la ventana guardada, mirando todas las ventanas
/// (el menú ⋮ de Chrome no pasa a estar al frente ni siempre avisa con un evento).
pub fn popups_de_la_guardada(ventanas: &[VentanaListada], g: Guardada) -> Vec<Rect> {
    ventanas
        .iter()
        .filter(|v| v.visible && v.hwnd != g.hwnd && v.rect.ancho > 0 && v.rect.alto > 0)
        .filter(|v| es_efimera(&v.datos, Some(g)))
        .map(|v| v.rect)
        .collect()
}

/// Valor de ExpandCollapseState que cuenta como "lo abrió" (Expanded o PartiallyExpanded).
pub fn cuenta_como_expandido(estado: i32) -> bool {
    estado == 1 || estado == 2
}

/// Hasta cuántos píxeles físicos de separación un popup cuenta como "pegado" al control.
const PEGADO_PX: i64 = 24;
/// Un popup más bajo que esto es un tooltip, no un menú.
const ALTO_MIN_MENU: u32 = 60;

fn separacion(a: Rect, b: Rect) -> (i64, i64) {
    let (ax0, ay0) = (i64::from(a.x), i64::from(a.y));
    let (ax1, ay1) = (ax0 + i64::from(a.ancho), ay0 + i64::from(a.alto));
    let (bx0, by0) = (i64::from(b.x), i64::from(b.y));
    let (bx1, by1) = (bx0 + i64::from(b.ancho), by0 + i64::from(b.alto));
    ((bx0 - ax1).max(ax0 - bx1).max(0), (by0 - ay1).max(ay0 - by1).max(0))
}

/// Un popup que se abrió recién, pegado al objetivo y con forma de menú: Ando abrió el control.
pub fn popup_nuevo_pegado(objetivo: Rect, antes: &[Rect], ahora: &[Rect]) -> bool {
    ahora.iter().filter(|p| !antes.contains(p)).any(|p| {
        let (dx, dy) = separacion(objetivo, *p);
        let forma_menu = p.alto >= ALTO_MIN_MENU && p.alto >= objetivo.alto.saturating_mul(2);
        forma_menu && dx <= PEGADO_PX && dy <= PEGADO_PX
    })
}

pub fn texto_marcas(cantidad: usize) -> String {
    if cantidad == 1 {
        "Te marqué un control".into()
    } else {
        format!("Te marqué {cantidad} controles")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const M1: Rect = Rect { x: 0, y: 0, ancho: 1920, alto: 1080 };
    const M2: Rect = Rect { x: 1920, y: 0, ancho: 2560, alto: 1440 };

    #[test]
    fn monitor_en_texto() {
        assert_eq!(texto_monitor(M2), "1920,0 2560x1440");
        assert_eq!(texto_monitor(Rect { x: -1280, y: -200, ancho: 1280, alto: 1024 }), "-1280,-200 1280x1024");
    }

    #[test]
    fn monitor_por_el_centro_del_control() {
        let r = Rect { x: 1900, y: 100, ancho: 100, alto: 20 };
        assert_eq!(monitor_para(r, &[M1, M2]), Some(1));
        assert_eq!(monitor_para(Rect { x: 10, y: 10, ancho: 50, alto: 20 }, &[M1, M2]), Some(0));
    }

    #[test]
    fn monitor_por_lo_que_se_ve_si_el_centro_cae_afuera() {
        let r = Rect { x: 1800, y: 1000, ancho: 200, alto: 200 };
        assert_eq!(monitor_para(r, &[M1, M2]), Some(1));
        assert_eq!(monitor_para(Rect { x: 9000, y: 9000, ancho: 10, alto: 10 }, &[M1, M2]), None);
        assert_eq!(monitor_para(Rect { x: 10, y: 10, ancho: 0, alto: 0 }, &[M1, M2]), None);
    }

    #[test]
    fn indice_pide_la_foto_actual_antes_que_el_numero() {
        assert_eq!(indice_en_foto(Some((7, 10)), 7, 3), Ok(2));
        assert_eq!(indice_en_foto(Some((7, 10)), 6, 3), Err(ERR_FOTO_VIEJA.into()));
        assert_eq!(indice_en_foto(Some((7, 10)), 6, 999), Err(ERR_FOTO_VIEJA.into()));
        assert_eq!(indice_en_foto(None, 7, 3), Err(ERR_FOTO_VIEJA.into()));
        assert_eq!(indice_en_foto(Some((7, 10)), 7, 999), Err(ERR_SIN_CONTROL.into()));
        assert_eq!(indice_en_foto(Some((7, 10)), 7, 0), Err(ERR_SIN_CONTROL.into()));
    }

    #[test]
    fn rect_vacio_o_fuera_de_pantalla_no_sirve() {
        let r = Rect { x: 10, y: 10, ancho: 50, alto: 20 };
        assert!(rect_utilizable(r, false));
        assert!(!rect_utilizable(r, true));
        assert!(!rect_utilizable(Rect { ancho: 0, ..r }, false));
        assert!(!rect_utilizable(Rect { alto: 0, ..r }, false));
    }

    #[test]
    fn errores_conocidos_pasan_y_el_resto_es_fallo_pc() {
        for c in [
            ERR_APAGADO, ERR_SIN_PC, ERR_SIN_VENTANA, ERR_SIN_CONTROLES, ERR_FOTO_VIEJA,
            ERR_SIN_CONTROL, ERR_OCUPADO, ERR_EN_CURSO, ERR_VENCIDO, ERR_INVALIDO, ERR_FALLO_PC,
        ] {
            assert_eq!(codigo_de_error(c), c);
        }
        assert_eq!(codigo_de_error("Error HRESULT 0x80004005"), ERR_FALLO_PC);
        assert_eq!(codigo_de_error(""), ERR_FALLO_PC);
    }

    #[test]
    fn ventanas_del_sistema_no_cuentan_como_ajenas() {
        for c in ["Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Progman", "WorkerW", "Windows.UI.Core.CoreWindow", "XamlExplorerHostIslandWindow"] {
            assert!(ventana_de_sistema(c), "{c}");
        }
        for c in ["Notepad", "Chrome_WidgetWin_1", "ApplicationFrameWindow", "#32770", ""] {
            assert!(!ventana_de_sistema(c), "{c}");
        }
    }

    fn ventana(clase: &'static str) -> VentanaNueva<'static> {
        VentanaNueva {
            clase,
            pid: 10,
            dueno_raiz: 0,
            tiene_dueno: false,
            ex_toolwindow: false,
            ex_noactivate: false,
            tiene_caption: true,
        }
    }

    const GUARDADA: Option<Guardada> = Some(Guardada { hwnd: 100, pid: 10 });

    #[test]
    fn el_menu_win32_del_mismo_proceso_no_reemplaza_la_ventana() {
        assert!(es_efimera(&ventana("#32768"), GUARDADA));
    }

    #[test]
    fn el_popup_sin_caption_del_mismo_proceso_es_efimero() {
        let popup = VentanaNueva { tiene_dueno: true, dueno_raiz: 100, tiene_caption: false, ..ventana("Chrome_WidgetWin_2") };
        assert!(es_efimera(&popup, GUARDADA));
        let toolwindow = VentanaNueva { ex_toolwindow: true, ..ventana("Chrome_WidgetWin_2") };
        assert!(es_efimera(&toolwindow, GUARDADA));
    }

    #[test]
    fn el_popup_cuyo_dueno_raiz_es_la_guardada_es_efimero_aunque_cambie_el_pid() {
        let popup = VentanaNueva { pid: 77, tiene_dueno: true, dueno_raiz: 100, ex_noactivate: true, ..ventana("Popup") };
        assert!(es_efimera(&popup, GUARDADA));
    }

    #[test]
    fn una_ventana_normal_o_de_otro_programa_si_reemplaza() {
        assert!(!es_efimera(&ventana("Chrome_WidgetWin_1"), GUARDADA));
        assert!(!es_efimera(&VentanaNueva { pid: 77, tiene_dueno: true, tiene_caption: false, dueno_raiz: 5, ..ventana("Popup") }, GUARDADA));
        assert!(!es_efimera(&VentanaNueva { pid: 77, ..ventana("#32768") }, GUARDADA));
        assert!(!es_efimera(&VentanaNueva { tiene_dueno: true, dueno_raiz: 100, ..ventana("#32770") }, GUARDADA));
    }

    #[test]
    fn sin_ventana_guardada_nada_es_efimero() {
        assert!(!es_efimera(&ventana("#32768"), None));
    }

    fn listada(hwnd: isize, rect: Rect, datos: VentanaNueva<'static>) -> VentanaListada<'static> {
        VentanaListada { hwnd, visible: true, rect, datos }
    }

    const MENU: Rect = Rect { x: 1500, y: 90, ancho: 380, alto: 600 };

    fn popup_chrome() -> VentanaNueva<'static> {
        VentanaNueva { tiene_dueno: true, dueno_raiz: 100, tiene_caption: false, ex_toolwindow: true, ..ventana("Chrome_WidgetWin_1") }
    }

    #[test]
    fn la_lista_devuelve_el_menu_abierto_de_la_guardada() {
        let g = Guardada { hwnd: 100, pid: 10 };
        let lista = [
            listada(100, Rect { x: 0, y: 0, ancho: 1920, alto: 1040 }, ventana("Chrome_WidgetWin_1")),
            listada(200, MENU, popup_chrome()),
        ];
        assert_eq!(popups_de_la_guardada(&lista, g), vec![MENU]);
    }

    #[test]
    fn la_lista_ignora_ocultas_vacias_la_guardada_y_ventanas_de_otros() {
        let g = Guardada { hwnd: 100, pid: 10 };
        let oculta = VentanaListada { visible: false, ..listada(201, MENU, popup_chrome()) };
        let vacia = listada(202, Rect { ancho: 0, ..MENU }, popup_chrome());
        let la_guardada = listada(100, MENU, popup_chrome());
        let otra = listada(203, MENU, VentanaNueva { pid: 77, dueno_raiz: 5, ..popup_chrome() });
        let normal = listada(204, MENU, ventana("Chrome_WidgetWin_1"));
        assert!(popups_de_la_guardada(&[oculta, vacia, la_guardada, otra, normal], g).is_empty());
    }

    #[test]
    fn la_lista_respeta_el_orden_y_devuelve_varios() {
        let g = Guardada { hwnd: 100, pid: 10 };
        let sub = Rect { x: 1120, y: 300, ancho: 380, alto: 200 };
        let lista = [listada(301, sub, popup_chrome()), listada(302, MENU, ventana("#32768"))];
        assert_eq!(popups_de_la_guardada(&lista, g), vec![sub, MENU]);
    }

    #[test]
    fn expandido_y_parcial_cuentan_colapsado_y_hoja_no() {
        assert!(cuenta_como_expandido(1));
        assert!(cuenta_como_expandido(2));
        assert!(!cuenta_como_expandido(0));
        assert!(!cuenta_como_expandido(3));
        assert!(!cuenta_como_expandido(-1));
    }

    const BOTON: Rect = Rect { x: 1840, y: 50, ancho: 40, alto: 36 };

    #[test]
    fn el_menu_que_se_abre_debajo_del_boton_cuenta() {
        assert!(popup_nuevo_pegado(BOTON, &[], &[MENU]));
    }

    #[test]
    fn el_menu_que_se_abre_arriba_del_boton_cuenta() {
        let boton = Rect { x: 1700, y: 1000, ancho: 40, alto: 36 };
        let menu = Rect { x: 1500, y: 1000 - 600 - 2, ancho: 300, alto: 600 };
        assert!(popup_nuevo_pegado(boton, &[], &[menu]));
    }

    #[test]
    fn el_menu_que_ya_estaba_abierto_no_cuenta() {
        assert!(!popup_nuevo_pegado(BOTON, &[MENU], &[MENU]));
    }

    #[test]
    fn un_popup_lejos_del_boton_no_cuenta() {
        assert!(!popup_nuevo_pegado(BOTON, &[], &[Rect { x: 200, y: 400, ancho: 380, alto: 600 }]));
        assert!(!popup_nuevo_pegado(BOTON, &[], &[Rect { y: 200, ..MENU }]));
    }

    #[test]
    fn un_tooltip_pegado_al_boton_no_cuenta() {
        let tooltip = Rect { x: 1700, y: 90, ancho: 220, alto: 30 };
        assert!(!popup_nuevo_pegado(BOTON, &[], &[tooltip]));
    }

    #[test]
    fn el_submenu_hacia_el_costado_tambien_cuenta() {
        let item = Rect { x: 1100, y: 300, ancho: 380, alto: 32 };
        let sub = Rect { x: 1484, y: 296, ancho: 300, alto: 400 };
        assert!(popup_nuevo_pegado(item, &[], &[sub]));
    }

    #[test]
    fn texto_del_globo_al_marcar() {
        assert_eq!(texto_marcas(1), "Te marqué un control");
        assert_eq!(texto_marcas(3), "Te marqué 3 controles");
    }
}
