/// Apertura del modo notas que puede llegar antes de que el notch haya cargado.
#[derive(Debug, Default)]
pub struct AperturaNotas {
    listo: bool,
    pendiente: bool,
}

impl AperturaNotas {
    /// `true`: emitir ya. Si el notch no está listo, deja la apertura pendiente y devuelve `false`.
    pub fn pedir(&mut self) -> bool {
        if self.listo {
            return true;
        }
        self.pendiente = true;
        false
    }

    /// El notch avisó que escucha. `true`: había una apertura pendiente y hay que emitirla ahora.
    pub fn marcar_listo(&mut self) -> bool {
        self.listo = true;
        std::mem::take(&mut self.pendiente)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pedir_antes_de_listo_queda_pendiente_y_no_emite() {
        let mut a = AperturaNotas::default();
        assert!(!a.pedir());
        assert!(a.marcar_listo());
    }

    #[test]
    fn listo_sin_pedido_no_emite() {
        let mut a = AperturaNotas::default();
        assert!(!a.marcar_listo());
    }

    #[test]
    fn pedir_con_el_notch_listo_emite_ya() {
        let mut a = AperturaNotas::default();
        a.marcar_listo();
        assert!(a.pedir());
        assert!(!a.marcar_listo());
    }

    #[test]
    fn el_pendiente_se_emite_una_sola_vez() {
        let mut a = AperturaNotas::default();
        a.pedir();
        a.pedir();
        assert!(a.marcar_listo());
        assert!(!a.marcar_listo());
    }
}
