# Origen de las fuentes

Las carpetas de `fuentes/` son copias fijas, sin editar, de repos MIT. Se copiaron como texto a un commit concreto para no bajar nada en runtime.

## fuentes/vercel-web-interface-guidelines

- Repo: https://github.com/vercel-labs/web-interface-guidelines
- Ruta en el repo: `command.md`
- Commit: 434b7f91364665f2f733b310ec54809bf8f37937 (2026-10-05)
- Licencia: MIT, Copyright (c) 2025 Vercel Labs
- En el original lo usa la skill web-design-guidelines de vercel-labs/agent-skills, que lo baja de la rama main en cada uso; acá se copió fijo.
- No se copió el `install.sh` del repo.

## fuentes/make-interfaces-feel-better

- Repo: https://github.com/jakubkrehel/make-interfaces-feel-better
- Ruta en el repo: `skills/make-interfaces-feel-better/`
- Commit: 1a2aa9695487dc6d2a59af28e34db9b1490ab181 (2026-11-16)
- Licencia: MIT, Copyright (c) 2026 Jakub Krehel
- Se renombró `SKILL.md` a `make-interfaces-feel-better.md` para que Claude Code no lo cargue como skill suelta. Quedan `animations.md`, `icons.md`, `performance.md`, `surfaces.md` y `typography.md` sin cambios.
- No se copió `agents/openai.yaml`.

## fuentes/emilkowalski-gestures

- Repo: https://github.com/emilkowalski/skills
- Ruta en el repo: `skills/gestures/SKILL.md`
- Commit: 64eb3deb9a5fbfa041faf783e0bc3fd635872e9c (2026-11-15)
- Licencia: MIT, Copyright (c) 2026 Emil Kowalski
- Se renombró `SKILL.md` a `gestures.md`.

## fuentes/emilkowalski-animation-performance

- Repo: https://github.com/emilkowalski/skills
- Ruta en el repo: `skills/animation-performance/SKILL.md`
- Commit: 64eb3deb9a5fbfa041faf783e0bc3fd635872e9c (2026-11-15)
- Licencia: MIT, Copyright (c) 2026 Emil Kowalski
- Se renombró `SKILL.md` a `animation-performance.md`.

## Cómo actualizar

1. Bajar los mismos archivos de un commit nuevo, solo como texto (nada de clonar para correr cosas).
2. Compararlos con las copias actuales con `diff`.
3. Revisar que lo nuevo no traiga scripts, hooks, fetch a la red ni directivas raras para el agente (saludos fijos, órdenes de instalar o ejecutar).
4. Reemplazar los archivos manteniendo los renombres de arriba, y actualizar el commit y la fecha en este archivo.
5. Nunca correr instaladores (`install.sh` u otros) de los repos de origen.
6. Revisar si `SKILL.md` necesita ajustar la tabla de traducción a Vue.
