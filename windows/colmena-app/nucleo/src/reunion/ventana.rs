//! Posición y tamaño de la ventana "Reunión" que se recuerdan entre aperturas.

use serde::{Deserialize, Serialize};

use crate::posicion::Rect;

/// Tamaño inicial lógico de la ventana la primera vez.
pub const TAMANO_INICIAL: (f64, f64) = (420.0, 640.0);
pub const ANCHO_MIN: u32 = 280;
pub const ALTO_MIN: u32 = 240;
const MAXIMO: u32 = 10_000;
/// Cuánto de la barra de título tiene que caer dentro de un monitor para poder agarrar la ventana.
const VISIBLE_MIN: i64 = 80;

/// Posición y tamaño en píxeles físicos.
#[derive(Serialize, Deserialize, Clone, Copy, Debug, PartialEq)]
pub struct VentanaGuardada {
    pub x: i32,
    pub y: i32,
    pub ancho: u32,
    pub alto: u32,
}

/// Lo guardado, si sirve: tamaño razonable y la barra de título a la vista en algún monitor.
/// `None` deja la ventana en su tamaño inicial y donde el sistema la ponga.
pub fn recordada(guardada: Option<VentanaGuardada>, monitores: &[Rect]) -> Option<VentanaGuardada> {
    let v = guardada?;
    if !(ANCHO_MIN..=MAXIMO).contains(&v.ancho) || !(ALTO_MIN..=MAXIMO).contains(&v.alto) {
        return None;
    }
    let (x1, x2) = (i64::from(v.x), i64::from(v.x) + i64::from(v.ancho));
    let y = i64::from(v.y);
    let a_la_vista = monitores.iter().any(|m| {
        let (mx, my) = (i64::from(m.x), i64::from(m.y));
        let ancho_visible = x2.min(mx + i64::from(m.ancho)) - x1.max(mx);
        y >= my && y < my + i64::from(m.alto) - VISIBLE_MIN && ancho_visible >= VISIBLE_MIN
    });
    a_la_vista.then_some(v)
}

#[cfg(test)]
mod tests {
    use super::*;

    const M: Rect = Rect { x: 0, y: 0, ancho: 1920, alto: 1080 };
    const V: VentanaGuardada = VentanaGuardada { x: 100, y: 80, ancho: 500, alto: 700 };

    #[test]
    fn devuelve_lo_guardado_si_esta_a_la_vista() {
        assert_eq!(recordada(Some(V), &[M]), Some(V));
    }

    #[test]
    fn sin_nada_guardado_no_hay_nada_que_recordar() {
        assert_eq!(recordada(None, &[M]), None);
    }

    #[test]
    fn un_monitor_que_ya_no_esta_descarta_la_posicion() {
        let v = VentanaGuardada { x: 2500, ..V };
        assert_eq!(recordada(Some(v), &[M]), None);
    }

    #[test]
    fn en_un_segundo_monitor_sigue_valida() {
        let m2 = Rect { x: 1920, y: 0, ancho: 1280, alto: 1024 };
        let v = VentanaGuardada { x: 2500, ..V };
        assert_eq!(recordada(Some(v), &[M, m2]), Some(v));
    }

    #[test]
    fn con_la_barra_de_titulo_fuera_de_pantalla_se_descarta() {
        let v = VentanaGuardada { y: -400, ..V };
        assert_eq!(recordada(Some(v), &[M]), None);
    }

    #[test]
    fn un_tamano_absurdo_se_descarta() {
        assert_eq!(recordada(Some(VentanaGuardada { ancho: 10, ..V }), &[M]), None);
        assert_eq!(recordada(Some(VentanaGuardada { alto: 20_000, ..V }), &[M]), None);
    }
}
