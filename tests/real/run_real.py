#!/usr/bin/env python3
"""Run xfa-extract against the real-world corpus and summarize.

This is a manual / dev check (needs network to fetch the corpus and is not part of CI).

    python fetch_corpus.py     # download ~14 real XFA forms into this directory
    python run_real.py         # run the installed CLI over each and report

Requires the package importable (`pip install -e .` from the repo root).
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CODES = {0: "XFA filled", 2: "not XFA", 3: "XFA empty", 4: "parse fail"}


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    pdfs = sorted(HERE.glob("*.pdf"))
    if not pdfs:
        print("no PDFs here — run `python fetch_corpus.py` first.")
        return 1
    print(f"Testing {len(pdfs)} real XFA samples\n")
    print(f"{'file':<32} {'exit':<4} {'kind':<9} {'fields':>6} {'filled':>6}  unchanged")
    print("-" * 78)
    summary = {}
    for pdf in pdfs:
        before = sha(pdf)
        raw = HERE / f"_raw_{pdf.stem}.xml"
        proc = subprocess.run(
            [sys.executable, "-m", "xfa_extract.cli", str(pdf),
             "--json", "--raw-out", str(raw), "--quiet"],
            capture_output=True, text=True)
        summary[proc.returncode] = summary.get(proc.returncode, 0) + 1
        kind = fc = fl = "-"
        try:
            d = json.loads(proc.stdout)
            kind, fc, fl = d.get("form_kind", "-"), d.get("field_count", "-"), d.get("filled_count", "-")
        except Exception:
            pass
        unchanged = "yes" if sha(pdf) == before else "NO!"
        print(f"{pdf.name:<32} {proc.returncode:<4} {str(kind):<9} {str(fc):>6} {str(fl):>6}  {unchanged}")

    print("\nexit-code distribution:")
    for c in sorted(summary):
        print(f"  exit {c} ({CODES.get(c, '?')}): {summary[c]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
