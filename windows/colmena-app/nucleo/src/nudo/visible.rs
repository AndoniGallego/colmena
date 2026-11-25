//! Cuándo la marca, la abejita y el globo se esconden: solo mientras la ventana de adelante no es la que la guía marca.

use super::pc::{es_efimera, Guardada, VentanaNueva};

#[derive(Debug, PartialEq, Eq, Clone, Copy)]
pub enum Cambio {
    Esconder,
    Mostrar,
    Nada,
}

/// `marcada`: la ventana sobre la que se dibujó (None si no hay dibujo). `hwnd`/`nueva`: la que pasó al frente.
pub fn decidir(marcada: Option<Guardada>, hwnd: isize, nueva: &VentanaNueva, es_colmena: bool, escondida: bool) -> Cambio {
    let Some(m) = marcada else {
        return Cambio::Nada;
    };
    if es_colmena || es_efimera(nueva, Some(m)) {
        return Cambio::Nada;
    }
    let es_la_marcada = hwnd == m.hwnd || (nueva.tiene_dueno && nueva.dueno_raiz == m.hwnd);
    match (es_la_marcada, escondida) {
        (true, true) => Cambio::Mostrar,
        (false, false) => Cambio::Esconder,
        _ => Cambio::Nada,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const M: Guardada = Guardada { hwnd: 100, pid: 7 };

    fn v(pid: u32) -> VentanaNueva<'static> {
        VentanaNueva {
            clase: "Chrome_WidgetWin_1",
            pid,
            dueno_raiz: 0,
            tiene_dueno: false,
            ex_toolwindow: false,
            ex_noactivate: false,
            tiene_caption: true,
        }
    }

    #[test]
    fn alt_tab_a_otra_app_esconde() {
        assert_eq!(decidir(Some(M), 200, &v(9), false, false), Cambio::Esconder);
    }

    #[test]
    fn otra_app_con_todo_ya_escondido_no_hace_nada() {
        assert_eq!(decidir(Some(M), 200, &v(9), false, true), Cambio::Nada);
    }

    #[test]
    fn volver_a_la_marcada_muestra() {
        assert_eq!(decidir(Some(M), 100, &v(7), false, true), Cambio::Mostrar);
    }

    #[test]
    fn la_marcada_ya_visible_no_hace_nada() {
        assert_eq!(decidir(Some(M), 100, &v(7), false, false), Cambio::Nada);
    }

    #[test]
    fn menu_o_popup_de_la_marcada_no_esconde() {
        let mut menu = v(7);
        menu.clase = "#32768";
        assert_eq!(decidir(Some(M), 300, &menu, false, false), Cambio::Nada);
        let mut popup = v(9);
        popup.tiene_dueno = true;
        popup.dueno_raiz = 100;
        popup.tiene_caption = false;
        assert_eq!(decidir(Some(M), 301, &popup, false, false), Cambio::Nada);
    }

    #[test]
    fn otra_ventana_del_mismo_programa_esconde() {
        // Otra ventana de Chrome no es la que la guía marca.
        assert_eq!(decidir(Some(M), 400, &v(7), false, false), Cambio::Esconder);
    }

    #[test]
    fn un_dialogo_de_la_marcada_cuenta_como_ella() {
        let dialogo = VentanaNueva { dueno_raiz: 100, tiene_dueno: true, ..v(7) };
        assert_eq!(decidir(Some(M), 401, &dialogo, false, false), Cambio::Nada);
        assert_eq!(decidir(Some(M), 401, &dialogo, false, true), Cambio::Mostrar);
    }

    #[test]
    fn ventanas_de_colmena_no_cambian_nada() {
        assert_eq!(decidir(Some(M), 500, &v(1), true, false), Cambio::Nada);
        assert_eq!(decidir(Some(M), 500, &v(1), true, true), Cambio::Nada);
    }

    #[test]
    fn sin_marca_no_hace_nada() {
        assert_eq!(decidir(None, 200, &v(9), false, false), Cambio::Nada);
        assert_eq!(decidir(None, 100, &v(7), false, true), Cambio::Nada);
    }
}
