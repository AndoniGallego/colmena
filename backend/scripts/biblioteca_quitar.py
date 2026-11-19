"""Quita ítems de la Biblioteca por filtro (con el servidor parado). Uso:

    cd backend && uv run python scripts/biblioteca_quitar.py --kind image --source send_user_file --dry-run
    cd backend && uv run python scripts/biblioteca_quitar.py --kind diagrama --session aaaa1111

Los filtros se combinan (AND) y hace falta al menos uno. Solo toca el índice y las copias propias.
"""
import argparse
import sys

from orquestador.biblioteca import KINDS, Library
from orquestador.config import data_dir, load_config, load_secret


def select(library: Library, kind: str, source: str, session: str) -> list:
    rows = [i for i in library.items.values()
            if (not kind or i["kind"] == kind) and (not source or i["source"] == source)
            and (not session or i["session_id"].startswith(session))]
    return sorted(rows, key=lambda i: (i["ts"], i["id"]))


def main(argv=None, library: Library = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--kind", choices=KINDS, default="")
    ap.add_argument("--source", choices=("artifact", "send_user_file", "diagrama"), default="")
    ap.add_argument("--session", default="", help="prefijo del id de sesión")
    ap.add_argument("--dry-run", action="store_true", help="solo lista, no quita nada")
    args = ap.parse_args(argv)
    if not (args.kind or args.source or args.session):
        ap.error("falta al menos un filtro (--kind, --source, --session)")
    if library is None:
        directory = data_dir()
        cfg = load_config(directory)
        library = Library(cfg, directory, load_secret(directory))
    rows = select(library, args.kind, args.source, args.session)
    for i in rows:
        print(f"{i['id']}  {i['ts'][:19]}  {i['kind']:<7} {i['source']:<14} {i['session_id'][:8]}  "
              f"{(i['title'] or i['caption'] or i['path'])[:60]}")
    if args.dry_run:
        print(f"[dry-run] {len(rows)} ítems se quitarían")
        return 0
    n = library.quitar([i["id"] for i in rows])
    print(f"Quitados {n} ítems")
    return 0


if __name__ == "__main__":
    sys.exit(main())
