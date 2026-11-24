//! Decide cuándo Colmena abre y cierra los Subtítulos en vivo de Windows (lógica pura).

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Plan {
    /// Hay que lanzar los Subtítulos en vivo.
    pub abrir: bool,
    /// Valor de "los abrió Colmena" para esta reunión (si abrir falla, el llamador lo baja a false).
    pub marca: bool,
}

/// Al empezar a escuchar: abre solo si no estaban abiertos; conserva la marca si ya eran suyos.
pub fn al_empezar(estaban_abiertos: bool, marca_previa: bool) -> Plan {
    let abrir = !estaban_abiertos;
    Plan { abrir, marca: abrir || marca_previa }
}

/// Margen para que Windows termine de abrir los Subtítulos que lanzó Colmena: mientras dura no se avisa "Sin subtítulos".
pub const GRACIA_APERTURA_MS: u64 = 15_000;
/// Durante el margen se los busca seguido, así la lectura arranca apenas aparecen.
pub const REBUSCA_EN_GRACIA_MS: u64 = 1_000;
/// Fuera del margen, cada cuánto se los vuelve a buscar.
pub const REBUSCA_MS: u64 = 5_000;

/// ¿Sigue el margen de apertura? `abiertos_en_ms` es cuándo los lanzó Colmena (None si no los lanzó).
pub fn en_gracia(abiertos_en_ms: Option<u64>, ahora_ms: u64) -> bool {
    abiertos_en_ms.is_some_and(|t| ahora_ms.saturating_sub(t) < GRACIA_APERTURA_MS)
}

/// Cada cuánto buscar los Subtítulos cuando todavía no se encontraron.
pub fn rebusca_ms(abiertos_en_ms: Option<u64>, ahora_ms: u64) -> u64 {
    if en_gracia(abiertos_en_ms, ahora_ms) { REBUSCA_EN_GRACIA_MS } else { REBUSCA_MS }
}

/// Al terminar: cierra los Subtítulos solo si los abrió Colmena.
pub fn al_terminar(abiertos_por_colmena: bool) -> bool {
    abiertos_por_colmena
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn recien_abiertos_por_colmena_no_avisa_y_busca_seguido() {
        assert!(en_gracia(Some(1_000), 1_500));
        assert_eq!(rebusca_ms(Some(1_000), 1_500), REBUSCA_EN_GRACIA_MS);
    }

    #[test]
    fn pasado_el_margen_o_si_no_los_abrio_avisa_y_busca_cada_5_s() {
        assert!(!en_gracia(Some(1_000), 1_000 + GRACIA_APERTURA_MS));
        assert!(!en_gracia(None, 10));
        assert_eq!(rebusca_ms(None, 10), REBUSCA_MS);
        assert_eq!(rebusca_ms(Some(0), GRACIA_APERTURA_MS), REBUSCA_MS);
    }

    #[test]
    fn si_estaban_cerrados_los_abre_y_los_marca_como_suyos() {
        assert_eq!(al_empezar(false, false), Plan { abrir: true, marca: true });
    }

    #[test]
    fn si_ya_estaban_abiertos_no_los_toca_ni_los_marca() {
        assert_eq!(al_empezar(true, false), Plan { abrir: false, marca: false });
    }

    #[test]
    fn al_volver_a_escuchar_conserva_la_marca_si_los_abrio_ella() {
        assert_eq!(al_empezar(true, true), Plan { abrir: false, marca: true });
    }

    #[test]
    fn si_los_cerraron_a_mano_vuelve_a_abrirlos() {
        assert_eq!(al_empezar(false, true), Plan { abrir: true, marca: true });
    }

    #[test]
    fn al_terminar_solo_cierra_los_que_abrio_ella() {
        assert!(al_terminar(true));
        assert!(!al_terminar(false));
    }
}
