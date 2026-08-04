#!/usr/bin/env python3
"""Run sql/04_queries.sql and write trimmed output for the evaluation meeting.

Generated locally by build.sh — not committed (contains swimmer names).
"""
from __future__ import annotations
import argparse
import os
import re
import sys

import duckdb

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
QUERIES = os.path.join(ROOT, "sql", "04_queries.sql")
DEFAULT_DB = os.path.join(ROOT, "build", "isa.duckdb")
DEFAULT_OUT = os.path.join(ROOT, "docs", "sample-query-output.txt")
ROW_LIMIT = 15


def split_blocks(sql: str):
    blocks, current, title = [], [], "preamble"
    for line in sql.splitlines():
        m = re.match(r"^--\s*(Q\d+)", line.strip())
        if m:
            if current:
                blocks.append((title, "\n".join(current).strip()))
            title, current = m.group(1), []
        else:
            current.append(line)
    if current:
        blocks.append((title, "\n".join(current).strip()))
    return blocks


def exec_sql(con, sql: str):
    for stmt in re.split(r";\s*\n", sql.strip()):
        stmt = stmt.strip()
        if stmt:
            con.execute(stmt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--limit", type=int, default=ROW_LIMIT)
    args = ap.parse_args()

    if not os.path.exists(args.db):
        sys.exit(f"database not found: {args.db}\n-> run: bash build.sh")

    sql = open(QUERIES, encoding="utf-8").read()
    # Views (v_swim, v_fmt) must be created before SELECTs — needs write, not read_only.
    con = duckdb.connect(args.db)
    lines = []

    for title, block in split_blocks(sql):
        if not block:
            continue
        upper = block.lstrip().upper()
        if title == "preamble" or upper.startswith("CREATE"):
            exec_sql(con, block)
            continue
        if not upper.startswith("SELECT"):
            continue
        try:
            df = con.execute(block).df()
        except Exception as exc:
            lines.append(f"\n===== {title} ERROR =====\n{exc}\n")
            continue
        n = len(df)
        shown = df.head(args.limit)
        lines.append(f"\n===== {title} =====  ({n} rows)\n")
        lines.append(shown.to_string(index=False))
        if n > args.limit:
            lines.append(f"\n... ({n - args.limit} more rows)")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines).lstrip() + "\n")
    print(f"[queries] wrote {args.out}")
    con.close()


if __name__ == "__main__":
    main()
