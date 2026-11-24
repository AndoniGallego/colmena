//! Copiloto de reuniones: lógica pura (sin Windows) para leer los Subtítulos en vivo.

pub mod dedup;
pub mod subtitulos;
pub mod tanda;
pub mod ventana;
pub mod visibilidad;

pub const ESTADO_ESCUCHANDO: &str = "escuchando";
pub const ESTADO_SIN_SUBTITULOS: &str = "sin_subtitulos";
pub const ESTADO_PAUSADO: &str = "pausado";
pub const ESTADO_APAGADO: &str = "apagado";

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Espera {
    /// Nada que hacer hasta el próximo pedido: el hilo duerme sin despertar.
    Bloquear,
    /// Hay lectura, rebúsqueda o diagnóstico en curso: despierta cada tick.
    ConTimeout,
}

pub fn espera(estado: &str, hay_diagnostico: bool) -> Espera {
    if hay_diagnostico || estado == ESTADO_ESCUCHANDO || estado == ESTADO_SIN_SUBTITULOS {
        Espera::ConTimeout
    } else {
        Espera::Bloquear
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn solo_despierta_por_tiempo_si_hay_algo_que_hacer() {
        assert_eq!(espera(ESTADO_ESCUCHANDO, false), Espera::ConTimeout);
        assert_eq!(espera(ESTADO_SIN_SUBTITULOS, false), Espera::ConTimeout); // rebusca cada 5 s
        assert_eq!(espera(ESTADO_PAUSADO, false), Espera::Bloquear);
        assert_eq!(espera(ESTADO_APAGADO, false), Espera::Bloquear);
        assert_eq!(espera(ESTADO_APAGADO, true), Espera::ConTimeout); // diagnóstico en curso
        assert_eq!(espera(ESTADO_PAUSADO, true), Espera::ConTimeout);
    }
}
