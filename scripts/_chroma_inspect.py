"""Read-only inspection of chroma.sqlite3 to gauge corruption blast radius."""

from __future__ import annotations

import os
import sqlite3

P = os.environ.get("CHROMA_SQLITE", r"D:\mcp_server\chroma_data\chroma.sqlite3")


def main() -> int:
    print("db:", P, "exists:", os.path.exists(P))
    con = sqlite3.connect(P)
    cur = con.cursor()
    tables = [r[0] for r in cur.execute(
        "select name from sqlite_master where type='table' order by name"
    ).fetchall()]
    print("\n=== row counts ===")
    for t in tables:
        try:
            n = cur.execute(f"select count(*) from '{t}'").fetchone()[0]
        except sqlite3.DatabaseError as exc:
            n = f"ERR {exc}"
        print(f"  {t}: {n}")

    print("\n=== collections ===")
    try:
        for row in cur.execute("select id, name, dimension from collections").fetchall():
            print(" ", row)
    except sqlite3.DatabaseError as exc:
        print("  collections read error:", exc)

    print("\n=== segments ===")
    try:
        for row in cur.execute("select id, type, scope, collection from segments").fetchall():
            print(" ", row)
    except sqlite3.DatabaseError as exc:
        print("  segments read error:", exc)

    print("\n=== integrity_check ===")
    try:
        print(" ", cur.execute("PRAGMA integrity_check").fetchone())
    except sqlite3.DatabaseError as exc:
        print("  integrity error:", exc)

    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
