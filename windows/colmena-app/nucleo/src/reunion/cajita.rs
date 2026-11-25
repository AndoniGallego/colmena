//! Qué hacer con la cajita de Subtítulos en vivo para que no se vea al compartir pantalla.

use crate::posicion::Rect;

pub const MOTIVO_ACOPLADA: &str = "cajita_acoplada";
pub const MOTIVO_ESCONDIDA: &str = "cajita_escondida";

/// Píxeles de tolerancia contra los bordes del monitor.
const MARGEN: i64 = 8;

/// Acoplada: ocupa casi todo el ancho de su monitor y está pegada arriba o abajo, o fuera del área
/// de trabajo (acoplada, Windows la saca del área de trabajo y la pone encima de la barra de tareas).
/// Minimizarla así deja una franja rota en el escritorio, por eso no se esconde.
pub fn es_acoplada(ventana: &Rect, monitor: &Rect, trabajo: &Rect) -> bool {
    let (vx, vy, va, vh) = (ventana.x as i64, ventana.y as i64, ventana.ancho as i64, ventana.alto as i64);
    let (mx, my, ma, mh) = (monitor.x as i64, monitor.y as i64, monitor.ancho as i64, monitor.alto as i64);
    let dentro = vx >= mx - MARGEN && vx + va <= mx + ma + MARGEN;
    let ancha = va * 100 >= ma * 95;
    let pegada = (vy - my).abs() <= MARGEN || (my + mh - (vy + vh)).abs() <= MARGEN;
    let (ty, th) = (trabajo.y as i64, trabajo.alto as i64);
    let fuera_del_trabajo = vy + vh <= ty + MARGEN || vy >= ty + th - MARGEN;
    dentro && ancha && (pegada || fuera_del_trabajo)
}

#[derive(Debug, PartialEq, Eq)]
pub enum Accion {
    Esconder,
    Avisar,
    Nada,
}

/// Decide una sola vez por reunión, así no le pelea a quien la vuelve a abrir a mano (Win+Ctrl+L crea otra
/// ventana). Si solo avisó porque estaba acoplada, una ventana nueva superpuesta sí se esconde.
#[derive(Default)]
pub struct Escondedor {
    vista: Option<isize>,
    escondida: bool,
}

impl Escondedor {
    pub fn ante(&mut self, hwnd: isize, acoplada: bool) -> Accion {
        if self.escondida || self.vista == Some(hwnd) {
            return Accion::Nada;
        }
        let ya_aviso = self.vista.is_some();
        self.vista = Some(hwnd);
        match (acoplada, ya_aviso) {
            (false, _) => {
                self.escondida = true;
                Accion::Esconder
            }
            (true, false) => Accion::Avisar,
            (true, true) => Accion::Nada,
        }
    }

    pub fn olvidar(&mut self) {
        *self = Self::default();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn r(x: i32, y: i32, ancho: u32, alto: u32) -> Rect {
        Rect { x, y, ancho, alto }
    }
    const FHD: Rect = Rect { x: 0, y: 0, ancho: 1920, alto: 1080 };

    #[test]
    fn acoplada_arriba_ocupa_todo_el_ancho() {
        assert!(es_acoplada(&r(0, 0, 1920, 200), &FHD, &FHD));
    }
    #[test]
    fn acoplada_abajo() {
        assert!(es_acoplada(&r(0, 880, 1920, 200), &FHD, &FHD));
    }
    #[test]
    fn superpuesta_al_medio_no_es_acoplada() {
        assert!(!es_acoplada(&r(400, 600, 800, 150), &FHD, &FHD));
    }
    #[test]
    fn acoplada_abajo_encima_de_la_barra_de_tareas() {
        // Barra de tareas de 48 px abajo; Subtítulos acoplado arriba de ella, fuera del área de trabajo.
        assert!(es_acoplada(&r(0, 832, 1920, 200), &FHD, &r(0, 0, 1920, 832)));
    }
    #[test]
    fn acoplada_arriba_con_area_de_trabajo_recortada() {
        assert!(es_acoplada(&r(0, 0, 1920, 200), &FHD, &r(0, 200, 1920, 832)));
    }
    #[test]
    fn superpuesta_ancha_dentro_del_area_de_trabajo_no_es_acoplada() {
        assert!(!es_acoplada(&r(0, 500, 1920, 200), &FHD, &r(0, 0, 1920, 1032)));
    }
    #[test]
    fn en_monitor_secundario() {
        let v = r(1920, 0, 2560, 180);
        assert!(es_acoplada(&v, &r(1920, 0, 2560, 1440), &r(1920, 0, 2560, 1440)));
        assert!(!es_acoplada(&v, &FHD, &FHD));
    }
    #[test]
    fn escondedor_una_vez_por_reunion() {
        let mut e = Escondedor::default();
        assert_eq!(e.ante(1, false), Accion::Esconder);
        assert_eq!(e.ante(1, false), Accion::Nada);
        // Ando la reabrió con Win+Ctrl+L (otra ventana): queda visible.
        assert_eq!(e.ante(2, false), Accion::Nada);
    }
    #[test]
    fn acoplada_y_despues_superpuesta_se_esconde() {
        let mut e = Escondedor::default();
        assert_eq!(e.ante(1, true), Accion::Avisar);
        assert_eq!(e.ante(2, true), Accion::Nada);
        assert_eq!(e.ante(3, false), Accion::Esconder);
        assert_eq!(e.ante(4, false), Accion::Nada);
    }
    #[test]
    fn acoplada_avisa_una_vez() {
        let mut e = Escondedor::default();
        assert_eq!(e.ante(1, true), Accion::Avisar);
        assert_eq!(e.ante(1, true), Accion::Nada);
    }
    #[test]
    fn olvidar_vuelve_a_decidir() {
        let mut e = Escondedor::default();
        e.ante(1, false);
        e.olvidar();
        assert_eq!(e.ante(1, false), Accion::Esconder);
    }
}
