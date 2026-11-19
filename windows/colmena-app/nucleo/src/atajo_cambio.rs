use crate::config::Accion;

/// Resultado de intentar cambiar el atajo global de una acción.
#[derive(Debug, PartialEq, Eq)]
pub struct CambioAtajo {
    /// Si hay que guardar el atajo nuevo en la config.
    pub guardar: bool,
    /// Atajo que queda activo (y tildado en el menú).
    pub activo: String,
    /// El atajo pedido lo usa otro programa.
    pub ocupado: bool,
}

/// Un atajo nuevo que no se pudo registrar no pisa al anterior.
pub fn decidir_cambio(anterior: &str, nuevo: &str, registro_ok: bool) -> CambioAtajo {
    if registro_ok {
        CambioAtajo { guardar: true, activo: nuevo.to_string(), ocupado: false }
    } else {
        CambioAtajo { guardar: false, activo: anterior.to_string(), ocupado: true }
    }
}

/// Renglón gris de la bandeja: "Notas: Ctrl+Alt+N".
pub fn linea_bandeja(accion: Accion, atajo: &str) -> String {
    format!("{}: {}", accion.nombre(), atajo)
}

/// Aviso de la bandeja cuando el atajo guardado no se pudo registrar.
pub fn aviso_ocupado(accion: Accion) -> String {
    format!("El atajo de {} lo usa otro programa", accion.nombre())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn textos_de_la_bandeja() {
        assert_eq!(linea_bandeja(Accion::Notas, "Ctrl+Alt+N"), "Notas: Ctrl+Alt+N");
        assert_eq!(linea_bandeja(Accion::Colmena, "Ctrl+Alt+C"), "Colmena: Ctrl+Alt+C");
        assert_eq!(aviso_ocupado(Accion::Notch), "El atajo de Notch lo usa otro programa");
    }

    #[test]
    fn indice_sigue_el_orden_de_todas() {
        for (i, a) in Accion::TODAS.into_iter().enumerate() {
            assert_eq!(a.indice(), i);
        }
    }

    #[test]
    fn registro_ok_guarda_y_activa_el_nuevo() {
        let c = decidir_cambio("Ctrl+Alt+N", "Ctrl+Alt+Space", true);
        assert_eq!(c, CambioAtajo { guardar: true, activo: "Ctrl+Alt+Space".into(), ocupado: false });
    }

    #[test]
    fn registro_fallido_no_guarda_y_deja_el_anterior() {
        let c = decidir_cambio("Ctrl+Alt+N", "Ctrl+Alt+Space", false);
        assert_eq!(c, CambioAtajo { guardar: false, activo: "Ctrl+Alt+N".into(), ocupado: true });
    }
}
