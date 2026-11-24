//! Qué ventanas se ocultan al compartir pantalla mientras se escucha una reunión.

/// Etiqueta de ventana y si se ve al compartir, en orden `notch`, `reunion`, `nudo`, `nudo-globo`.
pub fn afinidades(escuchando: bool, se_ve_al_compartir: bool) -> [(&'static str, bool); 4] {
    let nudo = se_ve_al_compartir;
    let reunion_o_notch = !escuchando || se_ve_al_compartir;
    [("notch", reunion_o_notch), ("reunion", reunion_o_notch), ("nudo", nudo), ("nudo-globo", nudo)]
}

#[cfg(test)]
mod tests {
    use super::*;

    fn de(a: &[(&'static str, bool)], label: &str) -> Option<bool> {
        a.iter().find(|(l, _)| *l == label).map(|(_, v)| *v)
    }

    #[test]
    fn la_ventana_reunion_sigue_la_regla_del_notch() {
        for (escuchando, se_ve) in [(true, false), (true, true), (false, false), (false, true)] {
            let a = afinidades(escuchando, se_ve);
            assert_eq!(de(&a, "reunion"), de(&a, "notch"), "escuchando={escuchando} se_ve={se_ve}");
            assert!(de(&a, "reunion").is_some());
        }
    }

    #[test]
    fn afinidades_mientras_escucha_siguen_el_interruptor() {
        assert_eq!(afinidades(true, false), [("notch", false), ("reunion", false), ("nudo", false), ("nudo-globo", false)]);
        assert_eq!(afinidades(true, true), [("notch", true), ("reunion", true), ("nudo", true), ("nudo-globo", true)]);
    }

    #[test]
    fn afinidades_sin_reunion_dejan_el_notch_como_hoy() {
        assert_eq!(afinidades(false, false), [("notch", true), ("reunion", true), ("nudo", false), ("nudo-globo", false)]);
    }

    #[test]
    fn afinidades_sin_reunion_el_nudo_sigue_el_interruptor() {
        assert_eq!(afinidades(false, true), [("notch", true), ("reunion", true), ("nudo", true), ("nudo-globo", true)]);
    }
}
