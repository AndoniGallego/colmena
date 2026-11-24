//! Captura por GDI de un rectángulo de la pantalla, achicado a `ancho` x `alto` (BGRA de arriba hacia abajo).
//! Solo a pedido: sin timers ni ganchos. Fuera de Windows responde `sin_ventana`.

use colmena_nucleo::posicion::Rect;

#[cfg(windows)]
pub fn capturar_bgra(recorte: Rect, ancho: u32, alto: u32) -> Result<Vec<u8>, String> {
    win::capturar(recorte, ancho, alto)
}

#[cfg(not(windows))]
pub fn capturar_bgra(_recorte: Rect, _ancho: u32, _alto: u32) -> Result<Vec<u8>, String> {
    Err(colmena_nucleo::nudo::ERR_SIN_VENTANA.into())
}

#[cfg(windows)]
mod win {
    use std::ffi::c_void;
    use std::ptr::null_mut;

    use colmena_nucleo::nudo::ERR_FALLO_PC;
    use colmena_nucleo::posicion::Rect;
    use windows_sys::Win32::Graphics::Gdi::{
        CreateCompatibleDC, CreateDIBSection, DeleteDC, DeleteObject, GdiFlush, GetDC, ReleaseDC,
        SelectObject, SetBrushOrgEx, SetStretchBltMode, StretchBlt, BITMAPINFO, BITMAPINFOHEADER,
        BI_RGB, DIB_RGB_COLORS, HALFTONE, HBITMAP, HDC, HGDIOBJ, SRCCOPY,
    };

    struct DcPantalla(HDC);
    impl Drop for DcPantalla {
        fn drop(&mut self) {
            unsafe { ReleaseDC(null_mut(), self.0) };
        }
    }

    struct DcMemoria(HDC);
    impl Drop for DcMemoria {
        fn drop(&mut self) {
            unsafe { DeleteDC(self.0) };
        }
    }

    struct Mapa(HBITMAP);
    impl Drop for Mapa {
        fn drop(&mut self) {
            unsafe { DeleteObject(self.0) };
        }
    }

    /// Devuelve al DC el objeto que tenía antes, para que el bitmap se pueda borrar.
    struct Seleccion {
        dc: HDC,
        previo: HGDIOBJ,
    }
    impl Drop for Seleccion {
        fn drop(&mut self) {
            unsafe { SelectObject(self.dc, self.previo) };
        }
    }

    fn fallo() -> String {
        ERR_FALLO_PC.to_string()
    }

    fn entero(v: u32) -> Result<i32, String> {
        i32::try_from(v).map_err(|_| fallo())
    }

    pub fn capturar(recorte: Rect, ancho: u32, alto: u32) -> Result<Vec<u8>, String> {
        if ancho == 0 || alto == 0 || recorte.ancho == 0 || recorte.alto == 0 {
            return Err(fallo());
        }
        let (a, h) = (entero(ancho)?, entero(alto)?);
        let (ra, rh) = (entero(recorte.ancho)?, entero(recorte.alto)?);
        let largo = usize::try_from(u64::from(ancho) * u64::from(alto) * 4).map_err(|_| fallo())?;
        // Las guardas se sueltan en orden inverso: selección, bitmap, DC de memoria y DC de pantalla.
        unsafe {
            let pantalla = GetDC(null_mut());
            if pantalla.is_null() {
                return Err(fallo());
            }
            let pantalla = DcPantalla(pantalla);
            let memoria = CreateCompatibleDC(pantalla.0);
            if memoria.is_null() {
                return Err(fallo());
            }
            let memoria = DcMemoria(memoria);

            let mut info: BITMAPINFO = std::mem::zeroed();
            info.bmiHeader.biSize = std::mem::size_of::<BITMAPINFOHEADER>() as u32;
            info.bmiHeader.biWidth = a;
            // Alto negativo: filas de arriba hacia abajo.
            info.bmiHeader.biHeight = -h;
            info.bmiHeader.biPlanes = 1;
            info.bmiHeader.biBitCount = 32;
            info.bmiHeader.biCompression = BI_RGB;
            let mut bits: *mut c_void = null_mut();
            let mapa = CreateDIBSection(pantalla.0, &info, DIB_RGB_COLORS, &mut bits, null_mut(), 0);
            if mapa.is_null() || bits.is_null() {
                if !mapa.is_null() {
                    DeleteObject(mapa);
                }
                return Err(fallo());
            }
            let mapa = Mapa(mapa);
            let previo = SelectObject(memoria.0, mapa.0);
            if previo.is_null() || previo as isize == -1 {
                return Err(fallo());
            }
            let _seleccion = Seleccion { dc: memoria.0, previo };

            SetStretchBltMode(memoria.0, HALFTONE);
            SetBrushOrgEx(memoria.0, 0, 0, null_mut());
            // Sin CAPTUREBLT: las ventanas en capas (el overlay del nudo) no entran en la imagen.
            if StretchBlt(memoria.0, 0, 0, a, h, pantalla.0, recorte.x, recorte.y, ra, rh, SRCCOPY) == 0 {
                return Err(fallo());
            }
            GdiFlush();
            Ok(std::slice::from_raw_parts(bits as *const u8, largo).to_vec())
        }
    }
}
