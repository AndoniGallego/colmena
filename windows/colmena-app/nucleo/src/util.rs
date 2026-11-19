/// Recorta el inicio de `buf` para que no supere `max` bytes, sin partir un carácter UTF-8.
pub fn recortar_inicio(buf: &mut String, max: usize) {
    while buf.len() > max {
        let mut extra = buf.len() - max;
        while extra < buf.len() && !buf.is_char_boundary(extra) {
            extra += 1;
        }
        buf.drain(..extra);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const STDERR_MAX: usize = 4096;

    #[test]
    fn recorte_no_parte_enye_extra_ca_en_medio_del_multibyte() {
        let mut buf = String::from("ñ") + &"a".repeat(STDERR_MAX - 1);
        assert_eq!(buf.len(), STDERR_MAX + 1);
        recortar_inicio(&mut buf, STDERR_MAX);
        assert!(buf.is_char_boundary(0));
        assert!(buf.len() <= STDERR_MAX);
        let esperado = "a".repeat(STDERR_MAX - 1);
        assert_eq!(buf, esperado, "cola exacta tras recorte en límite de ñ");
    }

    #[test]
    fn recorte_no_parte_jose_tail_con_e_acute_extra_dentro_del_enye_inicial() {
        let tail = " José fin";
        let prefix_as = STDERR_MAX + 1 - tail.len() - "ñ".len();
        let mut buf = String::from("ñ") + &"a".repeat(prefix_as) + tail;
        assert_eq!(buf.len(), STDERR_MAX + 1);
        recortar_inicio(&mut buf, STDERR_MAX);
        assert!(buf.is_char_boundary(0));
        assert!(buf.len() <= STDERR_MAX);
        assert!(buf.ends_with(" José fin"), "la cola conserva el é de José: {buf:?}");
        let esperado = "a".repeat(prefix_as) + tail;
        assert_eq!(buf, esperado);
    }
}
