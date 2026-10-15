#!/usr/bin/env python3
"""
Field-by-field parity check between the Python and Rust parse dumps.

Usage:
    python3 spikes/pubmed-ingest/compare_parity.py py.jsonl rust.jsonl [--show 3]
"""

import argparse
import json
import sys
from collections import Counter
from typing import Dict, Optional, Sequence

FIELDS = ("doi", "title", "abstract", "authors", "publication", "publication_date", "url",
          "mesh_terms", "keywords", "transparency_metadata")


def load(path: str) -> Dict[str, dict]:
    """Read a JSONL dump keyed by PMID (last occurrence wins, as in the merge)."""
    out: Dict[str, dict] = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            out[row["pmid"]] = row
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Compare two dumps; exit 1 if any field differs."""
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("python_dump")
    p.add_argument("rust_dump")
    p.add_argument("--show", type=int, default=3, help="examples to print per field")
    args = p.parse_args(argv)
    py, rs = load(args.python_dump), load(args.rust_dump)
    only_py, only_rs = set(py) - set(rs), set(rs) - set(py)
    mismatches: Counter = Counter()
    examples: Dict[str, list] = {}
    for pmid in set(py) & set(rs):
        for field in FIELDS:
            if py[pmid].get(field) != rs[pmid].get(field):
                mismatches[field] += 1
                examples.setdefault(field, []).append(pmid)
    common = len(set(py) & set(rs))
    print(json.dumps({"python": len(py), "rust": len(rs), "common": common,
                      "only_python": len(only_py), "only_rust": len(only_rs),
                      "field_mismatches": dict(mismatches),
                      "identical_articles": common - len({p for v in examples.values() for p in v})}))
    for field, pmids in examples.items():
        for pmid in pmids[:args.show]:
            print(f"--- {field} pmid={pmid}\n  py: {py[pmid].get(field)!r}\n  rs: {rs[pmid].get(field)!r}")
    return 1 if mismatches or only_py or only_rs else 0


if __name__ == "__main__":
    sys.exit(main())
