fn main() {
    tauri_build::try_build(
        tauri_build::Attributes::new().app_manifest(
            tauri_build::AppManifest::new().commands(&[
                "notch_tamano",
                "abrir_colmena",
                "mostrar_aviso",
                "guardar_origen",
                "notch_arrastrar",
                "notch_forma",
                "entorno_abrir",
                "entorno_cerrar",
                "entornos_estado",
                "abrir_ajuste_notebook",
                "guardar_notebook",
                "leer_notebook",
                "leer_atajos",
                "pausar_atajos",
                "reanudar_atajos",
                "probar_atajo",
                "guardar_atajo",
            ]),
        ),
    )
    .expect("tauri build");
}
