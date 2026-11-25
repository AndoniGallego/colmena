# nsis-extra

`Win/RestartManager.nsh` es una copia sin cambios del archivo del mismo nombre de NSIS
(github.com/kichik/nsis, carpeta `Include/Win/`), bajo la licencia zlib/libpng de NSIS.
El NSIS 3.08 de Ubuntu no lo trae y el instalador de Tauri lo incluye; `scripts/armar-instalador.sh`
lo suma con `-X!addincludedir` al llamar a `makensis`. No hace falta en la PC (el NSIS de Windows lo trae).
