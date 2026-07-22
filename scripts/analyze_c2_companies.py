"""Quick analysis of c2_company_names.csv quality."""
import csv
import re
from collections import Counter
from pathlib import Path

path = Path(__file__).resolve().parent.parent / "c2_company_names.csv"
rows = []
with path.open(encoding="utf-8-sig", errors="replace", newline="") as f:
    reader = csv.DictReader(f)
    for r in reader:
        rows.append(r)

print("Total rows:", len(rows))
names = [(r.get("Email", ""), r.get("Company Name", "") or "") for r in rows]
company_names = [n for _, n in names]

def is_dash_junk(s):
    s = s.strip()
    return s and all(c == "-" for c in s)

quotes = sum(1 for n in company_names if '"' in n)
dash_junk = sum(1 for n in company_names if is_dash_junk(n))
numeric = sum(1 for n in company_names if n.strip().isdigit())
empty = sum(1 for n in company_names if not n.strip())
mojibake = sum(1 for n in company_names if "â" in n or "Ã" in n)
print("With quotes:", quotes)
print("Dash-only:", dash_junk)
print("Numeric only:", numeric)
print("Empty:", empty)
print("Mojibake:", mojibake)
print("Unique names:", len(set(n.strip() for n in company_names)))

# Top 30 most common
ctr = Counter(n.strip() for n in company_names)
print("\nTop 30 company names:")
for name, cnt in ctr.most_common(30):
    print(f"  {cnt:6d}  {repr(name[:100])}")

# Sample weird patterns
print("\nSample mojibake:")
for e, n in names:
    if "â" in n:
        print(f"  {repr(n[:120])}")
        break

print("\nSample triple-quote prefix:")
for e, n in names:
    if n.startswith('"""'):
        print(f"  {repr(n[:120])}")
        break

print("\nSample parsed values (quotes/dash/numeric/mojibake):")
shown = 0
for e, n in names:
    if '"' in n or is_dash_junk(n) or n.strip().isdigit() or "â" in n or n.startswith("-"):
        print(f"  {repr(n[:140])}")
        shown += 1
        if shown >= 30:
            break

print("\nQuote-wrapped samples:")
shown = 0
for e, n in names:
    if '"' in n and not is_dash_junk(n) and not n.strip().isdigit():
        print(f"  {repr(n[:140])}")
        shown += 1
        if shown >= 25:
            break
