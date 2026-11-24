//! Fase de salida del nudo: las páginas animan y la ventana se oculta después.
//!
//! Rust no oculta las ventanas al limpiar: avisa a las páginas (que animan la salida) y las oculta
//! una sola vez, pasado `SALIDA_MS`, solo si en ese rato no llegó un dibujo o un globo nuevo.

/// Lo que dura la animación de salida en las páginas (globo y abejita).
pub const ANIMACION_SALIDA_MS: u64 = 200;
/// Espera única antes de ocultar: la animación más un margen.
pub const SALIDA_MS: u64 = 240;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Ocultar {
    pub nudo: bool,
    pub globo: bool,
}

/// Qué ventanas siguen sin uso al terminar la salida, según lo que hay a la vista en ese momento.
pub fn ocultar_tras_salida(hay_dibujo: bool, globo_visible: bool) -> Ocultar {
    Ocultar { nudo: !hay_dibujo, globo: !globo_visible }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sin_dibujo_ni_globo_oculta_las_dos() {
        assert_eq!(ocultar_tras_salida(false, false), Ocultar { nudo: true, globo: true });
    }

    #[test]
    fn un_dibujo_nuevo_durante_la_salida_no_se_oculta() {
        assert_eq!(ocultar_tras_salida(true, true), Ocultar { nudo: false, globo: false });
    }

    #[test]
    fn dibujo_sin_globo_oculta_solo_el_globo() {
        assert_eq!(ocultar_tras_salida(true, false), Ocultar { nudo: false, globo: true });
    }

    #[test]
    fn la_espera_alcanza_para_la_animacion_y_es_acotada() {
        assert!(SALIDA_MS >= ANIMACION_SALIDA_MS + 20);
        assert!(SALIDA_MS <= 400);
    }
}
