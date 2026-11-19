import { normalizeCambios, type Cambios } from '../api/cambiosApi'

const DIFF_TS = `@@ -10,7 +10,9 @@ export function conteo(p: Pruebas) {
   const ok = p.casos.filter((c) => c.resultado === 'ok').length
-  const falla = p.casos.filter((c) => c.resultado === 'fallo').length
+  const falla = p.casos.filter((c) => c.resultado === 'falla').length
+  const omitida = p.casos.filter((c) => c.resultado === 'omitida').length
   return { ok, falla }
 }
`
const DIFF_PY = `@@ -1,3 +1,5 @@
+from __future__ import annotations
+
 import json
 import re
`

export async function mockCambios(): Promise<Cambios> {
  return normalizeCambios({
    repo: true,
    rama: 'feature/kit-pruebas',
    base: 'main',
    commits: [
      { sha: 'a1b2c3d', titulo: 'feat: contar las omitidas' },
      { sha: 'e4f5a6b', titulo: 'fix: resultado falla' },
    ],
    commits_total: 2,
    sin_guardar: 1,
    archivos: [
      { path: 'frontend/src/lib/pruebas.ts', estado: 'M', adds: 2, dels: 1, binario: false, diff: DIFF_TS, truncado: false },
      { path: 'backend/orquestador/biblioteca.py', estado: 'M', adds: 2, dels: 0, binario: false, diff: DIFF_PY, truncado: false },
      { path: 'docs/captura.png', estado: 'A', adds: 0, dels: 0, binario: true, diff: '', truncado: false },
    ],
    truncado: false,
  })
}
