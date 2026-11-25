//! Convierte lo que muestra la caja de Subtítulos (texto que crece, se corre y se reescribe)
//! en frases nuevas sin repetir.

pub const QUIETO_MS: u64 = 3_000;
pub const ANCLA_CHARS: usize = 40;
pub const ANCLA_CORTA_CHARS: usize = 20;
pub const SOLAPE_MIN: usize = 8;
pub const COLA_MAX: usize = 4_000;

const TERMINADORES: [char; 4] = ['.', '?', '!', '…'];

#[derive(Default)]
pub struct Deduplicador {
    emitido: String,
    visible: String,
    cambio_ms: u64,
}

fn normalizar(t: &str) -> String {
    t.split_whitespace().collect::<Vec<_>>().join(" ")
}

fn plegar_char(c: char) -> Option<char> {
    if !c.is_alphanumeric() {
        return None;
    }
    let c = c.to_lowercase().next().unwrap_or(c);
    Some(match c {
        'á' | 'à' | 'ä' | 'â' => 'a',
        'é' | 'è' | 'ë' | 'ê' => 'e',
        'í' | 'ì' | 'ï' | 'î' => 'i',
        'ó' | 'ò' | 'ö' | 'ô' => 'o',
        'ú' | 'ù' | 'ü' | 'û' => 'u',
        'ñ' => 'n',
        otro => otro,
    })
}

/// Texto plegado (minúsculas, sin tildes, sin signos ni espacios) y, por cada char plegado,
/// el byte del original donde termina.
fn plegar(t: &str) -> (Vec<char>, Vec<usize>) {
    let mut cs = Vec::new();
    let mut fines = Vec::new();
    for (i, c) in t.char_indices() {
        if let Some(p) = plegar_char(c) {
            cs.push(p);
            fines.push(i + c.len_utf8());
        }
    }
    (cs, fines)
}

fn ultima_aparicion(pajar: &[char], aguja: &[char]) -> Option<usize> {
    if aguja.is_empty() || aguja.len() > pajar.len() {
        return None;
    }
    (0..=pajar.len() - aguja.len()).rev().find(|&i| &pajar[i..i + aguja.len()] == aguja)
}

fn recortar_inicio(t: &str) -> &str {
    t.trim_start_matches(|c: char| c.is_whitespace() || ",.;:…!?".contains(c))
}

fn estable(t: &str) -> &str {
    t.rfind(TERMINADORES).map_or("", |i| &t[..i + t[i..].chars().next().map_or(1, char::len_utf8)])
}

/// Largo (en caracteres) desde el que un renglón cortado se cierra con punto y no con raya.
const RENGLON_LARGO: usize = 40;

/// Subtítulos corta renglones a mitad de frase: cada salto pasa a ser punto, raya o espacio.
pub fn unir_lineas(t: &str) -> String {
    let mut out = String::new();
    let mut previo: Option<&str> = None;
    for renglon in t.split('\n').map(str::trim).filter(|r| !r.is_empty()) {
        if let Some(p) = previo {
            out.push_str(if p.ends_with(TERMINADORES) {
                " "
            } else if p.chars().count() >= RENGLON_LARGO {
                ". "
            } else {
                " — "
            });
        }
        out.push_str(renglon);
        previo = Some(renglon);
    }
    out
}

impl Deduplicador {
    pub fn observar(&mut self, visible: &str, ahora_ms: u64) -> Option<String> {
        let norm = normalizar(&unir_lineas(visible));
        if norm.is_empty() || norm == self.visible {
            return None;
        }
        self.visible = norm;
        self.cambio_ms = ahora_ms;
        let candidato = estable(&self.visible).to_string();
        self.emitir(&candidato)
    }

    pub fn tick(&mut self, ahora_ms: u64) -> Option<String> {
        if self.visible.is_empty() || ahora_ms.saturating_sub(self.cambio_ms) < QUIETO_MS {
            return None;
        }
        let candidato = self.visible.clone();
        self.emitir(&candidato)
    }

    pub fn cerrar(&mut self) -> Option<String> {
        let candidato = std::mem::take(&mut self.visible);
        self.emitir(&candidato)
    }

    pub fn memoria(&self) -> usize {
        self.emitido.chars().count()
    }

    fn emitir(&mut self, candidato: &str) -> Option<String> {
        let nuevo = recortar_inicio(self.parte_nueva(candidato)).trim_end().to_string();
        if nuevo.is_empty() {
            return None;
        }
        if !self.emitido.is_empty() {
            self.emitido.push(' ');
        }
        self.emitido.push_str(&nuevo);
        let exceso = self.memoria().saturating_sub(COLA_MAX);
        if exceso > 0 {
            let corte = self.emitido.char_indices().nth(exceso).map_or(self.emitido.len(), |(i, _)| i);
            self.emitido.drain(..corte);
        }
        Some(nuevo)
    }

    fn parte_nueva<'a>(&self, candidato: &'a str) -> &'a str {
        let (emi, _) = plegar(&self.emitido);
        if emi.is_empty() {
            return candidato;
        }
        let (cand, fines) = plegar(candidato);
        let desde = |k: usize| if k == 0 { 0 } else { fines[k - 1] };
        for n in [ANCLA_CHARS, ANCLA_CORTA_CHARS] {
            let ancla = &emi[emi.len() - n.min(emi.len())..];
            if let Some(i) = ultima_aparicion(&cand, ancla) {
                return &candidato[desde(i + ancla.len())..];
            }
        }
        let tope = emi.len().min(cand.len());
        for n in (SOLAPE_MIN..=tope).rev() {
            if emi[emi.len() - n..] == cand[..n] {
                return &candidato[desde(n)..];
            }
        }
        candidato
    }
}

/// Cuántas frases (de 15 letras plegadas o más) aparecen más de una vez: mide si el dedup deja repetidos.
pub fn contar_repetidas(textos: &[String]) -> usize {
    let mut vistas: std::collections::HashMap<String, usize> = std::collections::HashMap::new();
    for t in textos {
        for frase in t.split_inclusive(TERMINADORES) {
            let (cs, _) = plegar(frase);
            if cs.len() >= 15 {
                *vistas.entry(cs.into_iter().collect()).or_default() += 1;
            }
        }
    }
    vistas.values().filter(|&&n| n > 1).count()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn salto_tras_trozo_largo_es_punto() {
        assert_eq!(
            unir_lineas("hoy vamos a revisar los reembolsos de la semana\ny después vemos"),
            "hoy vamos a revisar los reembolsos de la semana. y después vemos"
        );
    }
    #[test]
    fn salto_tras_trozo_corto_es_raya() {
        assert_eq!(unir_lineas("bueno\nsigamos"), "bueno — sigamos");
    }
    #[test]
    fn salto_tras_terminador_es_espacio() {
        assert_eq!(unir_lineas("Listo.\nSigamos"), "Listo. Sigamos");
    }
    #[test]
    fn crlf_y_saltos_dobles_cuentan_uno() {
        assert_eq!(unir_lineas("bueno\r\n\nsigamos"), "bueno — sigamos");
    }
    #[test]
    fn largo_se_mide_en_caracteres() {
        // 39 caracteres con tildes (más de 40 bytes): sigue siendo corto.
        let t = "ñññññññññññññññññññññññññññññññññññññññ";
        assert_eq!(t.chars().count(), 39);
        assert_eq!(unir_lineas(&format!("{t}\nsigue")), format!("{t} — sigue"));
    }
    #[test]
    fn observar_usa_los_saltos() {
        let mut d = Deduplicador::default();
        let sale = d.observar("Primero lo de reembolsos y cuánto tarda cada uno\nDespués otra cosa.", 0);
        assert!(sale.as_deref().unwrap_or("").contains("cada uno. Después otra cosa."), "{sale:?}");
    }

    #[test]
    fn texto_que_crece_emite_solo_lo_nuevo() {
        let mut d = Deduplicador::default();
        assert_eq!(d.observar("Hola a todos.", 0).as_deref(), Some("Hola a todos."));
        assert_eq!(d.observar("Hola a todos. Hoy vemos", 100), None); // cola provisional
        assert_eq!(d.observar("Hola a todos. Hoy vemos reembolsos.", 200).as_deref(), Some("Hoy vemos reembolsos."));
    }
    #[test]
    fn cola_quieta_se_emite_a_los_3_segundos() {
        let mut d = Deduplicador::default();
        assert_eq!(d.observar("Hola che", 0), None);
        assert_eq!(d.tick(2_999), None);
        assert_eq!(d.tick(3_000).as_deref(), Some("Hola che"));
        assert_eq!(d.observar("Hola che, ¿cómo va?", 3_100).as_deref(), Some("¿cómo va?"));
    }
    #[test]
    fn caja_que_corre_lineas_viejas() {
        let mut d = Deduplicador::default();
        d.observar("Primero esto. Después aquello.", 0);
        assert_eq!(d.observar("Después aquello. Y por último lo otro.", 500).as_deref(), Some("Y por último lo otro."));
    }
    #[test]
    fn reescritura_de_puntuacion_no_duplica() {
        let mut d = Deduplicador::default();
        d.observar("hola que tal.", 0);
        assert_eq!(d.observar("Hola, ¿qué tal? Bien.", 400).as_deref(), Some("Bien."));
    }
    #[test]
    fn caja_reemplazada_entera_emite_todo() {
        let mut d = Deduplicador::default();
        d.observar("Uno dos tres.", 0);
        assert_eq!(d.observar("Algo totalmente distinto.", 900).as_deref(), Some("Algo totalmente distinto."));
    }
    #[test]
    fn mismo_texto_no_reemite_y_vacio_es_none() {
        let mut d = Deduplicador::default();
        d.observar("Listo.", 0);
        assert_eq!(d.observar("Listo.", 50), None);
        assert_eq!(d.observar("   ", 60), None);
    }
    #[test]
    fn cerrar_emite_la_cola_pendiente() {
        let mut d = Deduplicador::default();
        d.observar("Ya cierro. Y una cosa", 0);
        assert_eq!(d.cerrar().as_deref(), Some("Y una cosa"));
    }
    #[test]
    fn memoria_acotada() {
        let mut d = Deduplicador::default();
        for i in 0..2_000 { d.observar(&format!("Frase número {i}."), i * 10); }
        assert!(d.memoria() <= COLA_MAX);
    }
    #[test]
    fn repetidas_cuenta_frases_largas_que_salen_dos_veces() {
        let t = vec![
            "Hoy vemos los reembolsos del mes. Sí.".to_string(),
            "Sí. Hoy, vemos los reembolsos del mes!".to_string(),
            "Otra cosa distinta que se dijo recién.".to_string(),
        ];
        assert_eq!(contar_repetidas(&t), 1);
        assert_eq!(contar_repetidas(&[]), 0);
    }
}
