//! Armado y validación de atajos globales a partir de `KeyboardEvent.code`.

use crate::config::{Accion, Atajos};

const RESERVADA: &str = "Esa combinación la usa Windows: probá con otra";
const ALTGR: &str = "Ctrl+Alt con esa tecla es AltGr en el teclado español y escribe símbolos: probá con otra";

fn nombre_tecla(code: &str) -> Option<String> {
    if let Some(l) = code.strip_prefix("Key") {
        if l.len() == 1 && l.as_bytes()[0].is_ascii_uppercase() {
            return Some(l.to_string());
        }
    }
    if let Some(d) = code.strip_prefix("Digit") {
        if d.len() == 1 && d.as_bytes()[0].is_ascii_digit() {
            return Some(d.to_string());
        }
    }
    if let Some(n) = code.strip_prefix('F') {
        if let Ok(n) = n.parse::<u8>() {
            if (1..=12).contains(&n) && code == format!("F{n}") {
                return Some(code.to_string());
            }
        }
    }
    match code {
        "Space" | "ArrowUp" | "ArrowDown" | "ArrowLeft" | "ArrowRight" => Some(code.to_string()),
        _ => None,
    }
}

fn code_de_nombre(nombre: &str) -> Option<String> {
    let c = if nombre.len() == 1 && nombre.as_bytes()[0].is_ascii_uppercase() {
        format!("Key{nombre}")
    } else if nombre.len() == 1 && nombre.as_bytes()[0].is_ascii_digit() {
        format!("Digit{nombre}")
    } else {
        nombre.to_string()
    };
    nombre_tecla(&c).map(|_| c)
}

fn es_f(code: &str) -> bool {
    code.starts_with('F') && code != "F"
}

/// Arma el atajo en el formato del plugin (`Ctrl+Alt+K`) o explica por qué no sirve.
pub fn armar_atajo(ctrl: bool, alt: bool, shift: bool, code: &str) -> Result<String, String> {
    let reservada = matches!(
        (ctrl, alt, shift, code),
        (false, true, false, "F4")
            | (false, true, false, "Tab")
            | (false, true, false, "Space")
            | (true, false, false, "Escape")
            | (true, false, true, "Escape")
            | (true, true, false, "Delete")
    );
    if reservada {
        return Err(RESERVADA.into());
    }
    let Some(tecla) = nombre_tecla(code) else {
        return Err("Esa tecla no se puede usar: elegí una letra, un número, F1 a F12, Espacio o una flecha".into());
    };
    let n = ctrl as u8 + alt as u8 + shift as u8;
    let min = if es_f(code) { 1 } else { 2 };
    if n < min {
        return Err(if es_f(code) {
            "Sumá Ctrl, Alt o Shift".into()
        } else {
            "Usá al menos dos entre Ctrl, Alt y Shift".into()
        });
    }
    if ctrl && alt && (code == "KeyQ" || code == "KeyE" || code.starts_with("Digit")) {
        return Err(ALTGR.into());
    }
    let mut partes: Vec<&str> = Vec::new();
    if ctrl {
        partes.push("Ctrl");
    }
    if alt {
        partes.push("Alt");
    }
    if shift {
        partes.push("Shift");
    }
    partes.push(&tecla);
    Ok(partes.join("+"))
}

/// Un atajo guardado vale si es exactamente lo que armaría `armar_atajo`.
pub fn atajo_valido(s: &str) -> bool {
    let partes: Vec<&str> = s.split('+').collect();
    let Some((tecla, mods)) = partes.split_last() else {
        return false;
    };
    let (mut ctrl, mut alt, mut shift) = (false, false, false);
    for m in mods {
        match *m {
            "Ctrl" => ctrl = true,
            "Alt" => alt = true,
            "Shift" => shift = true,
            _ => return false,
        }
    }
    let Some(code) = code_de_nombre(tecla) else {
        return false;
    };
    armar_atajo(ctrl, alt, shift, &code).as_deref() == Ok(s)
}

/// Otra acción que ya usa ese atajo.
pub fn duplicado_de(atajos: &Atajos, accion: Accion, atajo: &str) -> Option<Accion> {
    Accion::TODAS
        .into_iter()
        .find(|a| *a != accion && atajos.get(*a) == atajo)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::{Accion, Atajos};

    fn armar(ctrl: bool, alt: bool, shift: bool, code: &str) -> Result<String, String> {
        armar_atajo(ctrl, alt, shift, code)
    }

    #[test]
    fn arma_los_defaults() {
        assert_eq!(armar(true, true, false, "KeyN").unwrap(), "Ctrl+Alt+N");
        assert_eq!(armar(true, true, false, "KeyM").unwrap(), "Ctrl+Alt+M");
        assert_eq!(armar(true, true, false, "KeyC").unwrap(), "Ctrl+Alt+C");
    }

    #[test]
    fn orden_canonico_de_modificadores() {
        assert_eq!(armar(true, false, true, "Space").unwrap(), "Ctrl+Shift+Space");
        assert_eq!(armar(true, true, true, "KeyK").unwrap(), "Ctrl+Alt+Shift+K");
    }

    #[test]
    fn mapea_teclas_permitidas() {
        assert_eq!(armar(true, false, true, "KeyZ").unwrap(), "Ctrl+Shift+Z");
        assert_eq!(armar(true, false, true, "Digit7").unwrap(), "Ctrl+Shift+7");
        assert_eq!(armar(true, false, true, "ArrowUp").unwrap(), "Ctrl+Shift+ArrowUp");
        assert_eq!(armar(true, false, true, "ArrowLeft").unwrap(), "Ctrl+Shift+ArrowLeft");
        assert_eq!(armar(true, false, true, "F12").unwrap(), "Ctrl+Shift+F12");
    }

    #[test]
    fn un_solo_modificador_no_alcanza() {
        assert!(armar(true, false, false, "KeyK").is_err());
        assert!(armar(false, true, false, "KeyK").is_err());
        assert!(armar(false, false, true, "KeyK").is_err());
        assert!(armar(false, false, false, "KeyK").is_err());
    }

    #[test]
    fn f1_a_f12_aceptan_un_modificador() {
        assert_eq!(armar(true, false, false, "F5").unwrap(), "Ctrl+F5");
        assert_eq!(armar(false, false, true, "F1").unwrap(), "Shift+F1");
        assert!(armar(false, false, false, "F5").is_err());
    }

    #[test]
    fn teclas_fuera_de_la_lista_se_rechazan() {
        for code in ["Enter", "Tab", "Backspace", "Numpad1", "Comma", "ShiftLeft", "F13", "Escape", ""] {
            assert!(armar(true, false, true, code).is_err(), "{code}");
        }
    }

    #[test]
    fn reservadas_de_windows() {
        for (c, a, s, code) in [
            (false, true, false, "F4"),
            (false, true, false, "Tab"),
            (false, true, false, "Space"),
            (true, false, false, "Escape"),
            (true, false, true, "Escape"),
            (true, true, false, "Delete"),
        ] {
            let e = armar(c, a, s, code).unwrap_err();
            assert!(e.contains("Windows"), "{code}: {e}");
        }
    }

    #[test]
    fn altgr_con_q_e_o_digito_se_rechaza() {
        for code in ["KeyQ", "KeyE", "Digit2", "Digit0"] {
            let e = armar(true, true, false, code).unwrap_err();
            assert!(e.contains("AltGr"), "{code}: {e}");
        }
        assert!(armar(true, true, false, "KeyW").is_ok());
        assert!(armar(true, false, true, "KeyQ").is_ok());
    }

    #[test]
    fn alt_f5_es_valido_y_alt_f4_no() {
        assert_eq!(armar(false, true, false, "F5").unwrap(), "Alt+F5");
        assert!(atajo_valido("Alt+F5"));
        assert!(!atajo_valido("Alt+F4"));
    }

    #[test]
    fn familia_alt_space() {
        assert!(armar(false, true, false, "Space").is_err());
        assert_eq!(armar(true, true, false, "Space").unwrap(), "Ctrl+Alt+Space");
        assert_eq!(armar(false, true, true, "Space").unwrap(), "Alt+Shift+Space");
        assert!(!atajo_valido("Alt+Space"));
        assert!(atajo_valido("Alt+Shift+Space"));
    }

    #[test]
    fn ctrl_alt_shift_con_digito_se_rechaza() {
        let e = armar(true, true, true, "Digit5").unwrap_err();
        assert!(e.contains("AltGr"), "{e}");
        assert!(!atajo_valido("Ctrl+Alt+Shift+5"));
    }

    #[test]
    fn valido_acepta_lo_guardado_en_el_mismo_formato() {
        for s in ["Ctrl+Alt+N", "Ctrl+Alt+M", "Ctrl+Alt+C", "Ctrl+Shift+Space", "Ctrl+Alt+Space", "Ctrl+F5", "Ctrl+Alt+Shift+K", "Ctrl+Shift+ArrowUp"] {
            assert!(atajo_valido(s), "{s}");
        }
    }

    #[test]
    fn valido_rechaza_lo_que_no_cumple() {
        for s in ["", "Alt+F4", "ctrl+alt+n", "Ctrl+Alt+Q", "Ctrl+N", "Win+Ctrl+N", "Alt+Ctrl+N", "Ctrl+Ctrl+N", "Ctrl+Alt+", "Ctrl+Alt+Enter", "Ctrl+Alt+N+M"] {
            assert!(!atajo_valido(s), "{s}");
        }
    }

    #[test]
    fn detecta_duplicado_entre_acciones() {
        let a = Atajos::default();
        assert_eq!(duplicado_de(&a, Accion::Notas, "Ctrl+Alt+M"), Some(Accion::Notch));
        assert_eq!(duplicado_de(&a, Accion::Notas, "Ctrl+Alt+N"), None);
        assert_eq!(duplicado_de(&a, Accion::Colmena, "Ctrl+Shift+Space"), None);
        assert_eq!(duplicado_de(&a, Accion::Notas, "Ctrl+Alt+V"), Some(Accion::Guia));
        assert!(atajo_valido("Ctrl+Alt+V"));
    }
}
