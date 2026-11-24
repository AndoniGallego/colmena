//! Junta frases sueltas en tandas de hasta `TANDA_MS` o `TANDA_MAX` caracteres.

pub const TANDA_MS: u64 = 5_000;
pub const TANDA_MAX: usize = 1_000;

#[derive(Default)]
pub struct Tanda {
    texto: String,
    inicio_ms: u64,
}

impl Tanda {
    fn largo(&self) -> usize {
        self.texto.chars().count()
    }

    pub fn agregar(&mut self, texto: &str, ahora_ms: u64) -> Vec<String> {
        let mut salidas = Vec::new();
        let texto = texto.trim();
        if texto.is_empty() {
            return salidas;
        }
        if !self.texto.is_empty() && ahora_ms.saturating_sub(self.inicio_ms) >= TANDA_MS {
            salidas.extend(self.vaciar());
        }
        if self.texto.is_empty() {
            self.inicio_ms = ahora_ms;
        } else {
            self.texto.push(' ');
        }
        self.texto.push_str(texto);
        while self.largo() > TANDA_MAX {
            let corte = self.texto.char_indices().nth(TANDA_MAX).map_or(self.texto.len(), |(i, _)| i);
            let resto = self.texto.split_off(corte);
            salidas.push(std::mem::replace(&mut self.texto, resto));
            self.inicio_ms = ahora_ms;
        }
        salidas
    }

    pub fn tick(&mut self, ahora_ms: u64) -> Option<String> {
        if !self.texto.is_empty() && ahora_ms.saturating_sub(self.inicio_ms) >= TANDA_MS {
            return self.vaciar();
        }
        None
    }

    pub fn vaciar(&mut self) -> Option<String> {
        let t = std::mem::take(&mut self.texto);
        let t = t.trim().to_string();
        (!t.is_empty()).then_some(t)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tanda_junta_hasta_5_segundos() {
        let mut t = Tanda::default();
        assert!(t.agregar("uno", 0).is_empty());
        assert!(t.agregar("dos", 4_000).is_empty());
        assert_eq!(t.tick(4_999), None);
        assert_eq!(t.tick(5_000).as_deref(), Some("uno dos"));
        assert_eq!(t.tick(9_000), None);
    }

    #[test]
    fn tanda_corta_al_pasar_1000_caracteres() {
        let mut t = Tanda::default();
        let largo = "á".repeat(1_500); // caracteres, no bytes
        let salidas = t.agregar(&largo, 0);
        assert_eq!(salidas.len(), 1);
        assert_eq!(salidas[0].chars().count(), 1_000);
        assert_eq!(t.vaciar().map(|s| s.chars().count()), Some(500));
    }

    #[test]
    fn agregar_tarde_cierra_la_tanda_vieja_primero() {
        let mut t = Tanda::default();
        t.agregar("uno", 0);
        assert_eq!(t.agregar("dos", 6_000), vec!["uno".to_string()]);
        assert_eq!(t.vaciar().as_deref(), Some("dos"));
    }
}
