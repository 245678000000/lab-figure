"""Summarise a data table so a figure template can be chosen and mapped.

Prints one line per column: kind, missing count, distinct values, a range or
level counts, and a role hint (binary outcome/group, survival time, survival
event, id). Detects two-row Excel headers (a group-title row above the real
column names) and says how to read them in R.

    python inspect_data.py data.xlsx [--sheet Cohort10] [--header-row 1]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd

TIME_RE = re.compile(r"(os|pfs|dfs|rfs|efs|survival|follow).*(time|month|day|year)|"
                     r"(time|month|day|year).*(os|pfs|dfs|rfs|efs)", re.I)
EVENT_RE = re.compile(r"status|event|censor|dead|death|progress", re.I)
ID_RE = re.compile(r"(^|[_ .])(id|sample|patient|barcode)([_ .]|$)", re.I)


def read_tables(path: Path, sheet: str | None, header_row: int | None) -> dict[str, tuple[pd.DataFrame, int]]:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        sheets = [sheet] if sheet else pd.ExcelFile(path).sheet_names
        out = {}
        for s in sheets:
            hr = header_row if header_row is not None else detect_header_row(path, s)
            out[s] = (pd.read_excel(path, sheet_name=s, header=hr), hr)
        return out
    sep = "\t" if suffix in {".tsv", ".tab"} else None
    hr = header_row or 0
    return {path.name: (pd.read_csv(path, sep=sep, engine="python", header=hr), hr)}


def detect_header_row(path: Path, sheet: str) -> int:
    """Return 1 when row 0 is a sparse group-title row above the real header."""
    top = pd.read_excel(path, sheet_name=sheet, header=None, nrows=3)
    if len(top) < 2:
        return 0
    first, second = top.iloc[0], top.iloc[1]
    first_filled = first.notna().mean()
    second_text = second.map(lambda v: isinstance(v, str)).mean()
    return 1 if first_filled < 0.5 and second_text > 0.8 else 0


def describe(col: pd.Series, n_rows: int, max_levels: int) -> dict:
    s = col.dropna()
    info: dict = {"missing": int(col.isna().sum()), "distinct": int(s.nunique())}
    numeric = pd.to_numeric(s, errors="coerce")
    is_numeric = len(s) > 0 and numeric.notna().mean() > 0.95
    name = str(col.name)

    if is_numeric:
        info["kind"] = "numeric"
        info["range"] = [float(numeric.min()), float(numeric.median()), float(numeric.max())]
    elif info["distinct"] <= max_levels:
        info["kind"] = "categorical"
    else:
        info["kind"] = "text"
    if info["distinct"] <= max_levels:
        info["levels"] = {str(k): int(v) for k, v in s.astype(str).value_counts().items()}
    elif info["kind"] == "text":
        info["examples"] = [str(v) for v in s.head(3)]

    roles = []
    if info["distinct"] == 2:
        roles.append("binary: outcome or group")
        if is_numeric and EVENT_RE.search(name):
            roles.append("survival event")
    if is_numeric and TIME_RE.search(name):
        roles.append("survival time")
    if ID_RE.search(name) or (info["kind"] == "text" and info["distinct"] == n_rows):
        roles.append("id")
    if is_numeric and info["distinct"] > max_levels and not roles:
        roles.append("continuous: score / feature")
    if roles:
        info["roles"] = roles
    return info


def fmt_num(x: float) -> str:
    return f"{x:.4g}"


def print_table(name: str, df: pd.DataFrame, header_row: int, path: Path, max_levels: int) -> dict:
    df = df.dropna(how="all").dropna(axis=1, how="all")
    cols = {str(c): describe(df[c], len(df), max_levels) for c in df.columns}
    print(f"## {name}: {len(df)} rows x {len(df.columns)} columns")
    if header_row:
        print(f"NOTE: row {header_row + 1} holds the column names (row 1 is group titles).")
        if path.suffix.lower().startswith(".xls"):
            print(f'      R: readxl::read_excel("{path.name}", sheet = "{name}", skip = {header_row})')
    odd = [c for c in cols if re.search(r"[^A-Za-z0-9_.]", c)]
    if odd:
        print(f"NOTE: {len(odd)} column names contain spaces/symbols; pass them to lab_* as strings, "
              "and use check.names = FALSE / readxl so they are kept as-is.")
    for c, info in cols.items():
        parts = [info["kind"], f"missing {info['missing']}", f"distinct {info['distinct']}"]
        if "range" in info:
            parts.append("min/med/max " + "/".join(fmt_num(v) for v in info["range"]))
        if "levels" in info and (info["kind"] != "numeric" or info["distinct"] <= 3):
            parts.append("levels " + ", ".join(f"{k} ({v})" for k, v in info["levels"].items()))
        if "examples" in info:
            parts.append("e.g. " + " | ".join(info["examples"]))
        if "roles" in info:
            parts.append("-> " + "; ".join(info["roles"]))
        print(f"- {c}: " + ", ".join(parts))
    print()
    return {"rows": len(df), "header_row": header_row, "columns": cols}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", type=Path)
    ap.add_argument("--sheet", help="only this Excel sheet")
    ap.add_argument("--header-row", type=int, help="0-based row holding column names (default: auto)")
    ap.add_argument("--max-levels", type=int, default=12, help="list levels up to this many distinct values")
    ap.add_argument("--json", action="store_true", help="also write <data>.inspect.json next to the data")
    args = ap.parse_args()

    if not args.path.exists():
        print(f"not found: {args.path}", file=sys.stderr)
        return 2
    report = {}
    for name, (df, hr) in read_tables(args.path, args.sheet, args.header_row).items():
        report[name] = print_table(name, df, hr, args.path, args.max_levels)
    if args.json:
        out = args.path.with_suffix(args.path.suffix + ".inspect.json")
        out.write_text(json.dumps(report, indent=1, ensure_ascii=False))
        print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
