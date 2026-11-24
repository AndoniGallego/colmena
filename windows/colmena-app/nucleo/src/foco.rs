//! Orden de los pasos para darle (o sacarle) el teclado al notch.
//!
//! En Windows traer la ventana al frente no alcanza: WebView2 deja el teclado en la ventana nativa
//! y el campo no recibe las teclas hasta que el controlador mueve el foco adentro (`MoveFocus`).

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum PasoFoco {
    /// La ventana estaba oculta.
    Mostrar,
    /// Saca `WS_EX_NOACTIVATE`: sin esto Windows no la activa.
    PermitirActivar,
    /// Vuelve a poner `WS_EX_NOACTIVATE`: mostrarla no le roba el foco a la ventana de Ando.
    ImpedirActivar,
    /// `SetForegroundWindow` (el atajo le da permiso a Colmena).
    TraerAlFrente,
    /// `MoveFocus` del controlador de WebView2: el teclado entra a la página.
    EnfocarContenido,
}

pub fn pasos_foco(visible: bool, foco: bool) -> Vec<PasoFoco> {
    if !foco {
        return vec![PasoFoco::ImpedirActivar];
    }
    let mut pasos = Vec::with_capacity(4);
    if !visible {
        pasos.push(PasoFoco::Mostrar);
    }
    pasos.extend([PasoFoco::PermitirActivar, PasoFoco::TraerAlFrente, PasoFoco::EnfocarContenido]);
    pasos
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn con_foco_y_oculto_muestra_antes_de_traer_al_frente() {
        assert_eq!(
            pasos_foco(false, true),
            vec![PasoFoco::Mostrar, PasoFoco::PermitirActivar, PasoFoco::TraerAlFrente, PasoFoco::EnfocarContenido]
        );
    }

    #[test]
    fn con_foco_y_visible_no_vuelve_a_mostrar() {
        assert_eq!(
            pasos_foco(true, true),
            vec![PasoFoco::PermitirActivar, PasoFoco::TraerAlFrente, PasoFoco::EnfocarContenido]
        );
    }

    #[test]
    fn el_contenido_se_enfoca_siempre_al_final() {
        for visible in [false, true] {
            assert_eq!(pasos_foco(visible, true).last(), Some(&PasoFoco::EnfocarContenido));
        }
    }

    #[test]
    fn sin_foco_solo_impide_activar() {
        assert_eq!(pasos_foco(true, false), vec![PasoFoco::ImpedirActivar]);
        assert_eq!(pasos_foco(false, false), vec![PasoFoco::ImpedirActivar]);
    }
}
