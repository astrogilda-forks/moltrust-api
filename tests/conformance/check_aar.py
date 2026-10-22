"""Hold a score_aar.py run to the per-member results it was published with.

usage: python -I tests/conformance/check_aar.py --scored <out.tsv> \
           --expected tests/conformance/aar_68_members.tsv \
           --manifest <corpus-dir>/MANIFEST.json --digest <corpusDigest>

The expected file is the TSV of the 68-member run at vectors-agent-audit-record
v0.18.1 (agent-evidence-vectors 33d5451). Every cell of every member must match
what the run writes now: the verdict of each intake, the stage that gave it, the
conformance flag, the cause class and the cause text. The member set must match
in both directions, and the MANIFEST must declare the pinned corpusDigest, so a
corpus that moved fails by name instead of changing a total.

Exit 0 when every cell matches, 1 when any differs, 2 on unusable input.
--self-test checks that the comparison itself can fail: it changes one expected
cell, drops one expected member and offers a different digest, and requires each
to be caught, so a checker that matches everything cannot pass.
"""

import argparse
import csv
import json
import sys
from pathlib import Path


def load_tsv(path):
    text = Path(path).read_text(encoding="utf-8").replace("\r\n", "\n")
    lines = text.splitlines()
    if not lines:
        raise SystemExit(f"{path}: empty")
    rows = list(csv.DictReader(lines, delimiter="\t"))
    header = lines[0].split("\t")
    if "draftId" not in header or "conforms" not in header:
        raise SystemExit(f"{path}: not a score_aar.py table (header {header})")
    return header, rows


def manifest_ids(path):
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    return manifest.get("corpusDigest"), [v["draftId"] for v in manifest["vectors"]]


def compare(header, scored, expected, corpus_ids):
    """Return the list of differences between a scored run and the expected table."""
    diffs = []
    got = {r["draftId"]: r for r in scored}
    want = {r["draftId"]: r for r in expected}
    for member in corpus_ids:
        if member not in want:
            diffs.append(f"{member}: in the corpus but absent from the expected table")
    for member in want:
        if member not in corpus_ids:
            diffs.append(f"{member}: in the expected table but absent from the corpus")
        if member not in got:
            diffs.append(f"{member}: not scored")
    for member in got:
        if member not in want:
            diffs.append(f"{member}: scored but absent from the expected table")
    for member, row in want.items():
        if member not in got:
            continue
        for column in header:
            if got[member].get(column) != row.get(column):
                diffs.append(f"{member} {column}: got {got[member].get(column)!r}, published {row.get(column)!r}")
    return diffs


def summary(rows):
    conform = sum(1 for r in rows if r["conforms"] == "yes")
    classes = {}
    for r in rows:
        if r["conforms"] != "yes":
            classes[r["cause_class"]] = classes.get(r["cause_class"], 0) + 1
    return conform, classes


def digest_matches(declared, digest):
    """True when the manifest declares exactly the pinned digest, and it is not a placeholder."""
    return declared == digest and declared != "0" * 64


def self_test(header, scored, expected, corpus_ids, declared, digest):
    problems = []
    flipped = [dict(r) for r in expected]
    column = "conforms"
    flipped[0][column] = "no" if flipped[0][column] == "yes" else "yes"
    if not compare(header, scored, flipped, corpus_ids):
        problems.append("a changed expected cell went unnoticed")
    if not compare(header, scored, expected[1:], corpus_ids):
        problems.append("a dropped expected member went unnoticed")
    if digest_matches(declared, "f" * 64):
        problems.append("a wrong digest was accepted")
    if digest_matches("0" * 64, "0" * 64):
        problems.append("a placeholder digest was accepted")
    if not digest_matches(declared, digest):
        problems.append("the pinned digest does not match the manifest")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scored", required=True)
    ap.add_argument("--expected", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--digest", required=True)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    declared, corpus_ids = manifest_ids(args.manifest)
    if not digest_matches(declared, args.digest):
        print(f"corpusDigest {declared} is not the pinned {args.digest}")
        return 2
    header, expected = load_tsv(args.expected)
    scored_header, scored = load_tsv(args.scored)
    if scored_header != header:
        print(f"the scored table has columns {scored_header}, the published one {header}")
        return 2

    if args.self_test:
        problems = self_test(header, scored, expected, corpus_ids, declared, args.digest)
        if problems:
            for p in problems:
                print(f"self-test: {p}")
            return 1
        print("self-test: a changed cell, a dropped member and a wrong digest are each caught")
        return 0

    diffs = compare(header, scored, expected, corpus_ids)
    conform, classes = summary(scored)
    print(f"corpusDigest {declared}; {len(expected)} members published, {len(scored)} scored")
    print(f"  {conform} of {len(scored)} conform; not conforming by cause: {dict(sorted(classes.items()))}")
    for d in diffs:
        print(f"  DIFFERS {d}")
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.exit(main())
