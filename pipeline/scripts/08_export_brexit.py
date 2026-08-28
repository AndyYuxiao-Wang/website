"""
Exports the "2016" sheet of Brexit.xlsx (estimated EU referendum Leave/Remain
vote by pre-2024-boundary constituency) into a JSON file shaped like the
other web/data/elections/*.json files, so it can be plugged into the map as
a normal "election" with LEAVE and REMAIN as the two parties.

Usage:
    py 08_export_brexit.py
"""
import re
import openpyxl
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent
SOURCE = PROJECT_ROOT / "Brexit.xlsx"
SVG_2010 = PROJECT_ROOT / "web" / "maps" / "conmap_2010.svg"
OUTPUT = PROJECT_ROOT / "web" / "data" / "elections" / "eu2016.json"

# The workbook's constituency names are mostly identical to the pre-2024
# boundary map's labels. A handful of exceptions need a direct rename
# ("North X"/"South X" word order, a missing accent), and a separate handful
# of comma-joined city seats (e.g. "Birmingham, Erdington") drop the comma on
# the map while OTHER comma-joined seats (e.g. "Ayr, Carrick and Cumnock")
# keep theirs - so comma-stripping is only tried as a fallback, never first.
NAME_FIXES = {
    "Ynys Mon": "Ynys Môn",
    "North Swindon": "Swindon North",
    "South Swindon": "Swindon South",
}


def resolve(raw_name, svg_labels):
    if raw_name in svg_labels:
        return raw_name
    fixed = NAME_FIXES.get(raw_name)
    if fixed in svg_labels:
        return fixed
    stripped = raw_name.replace(", ", " ")
    if stripped in svg_labels:
        return stripped
    return None


def main():
    svg_labels = set(re.findall(r'inkscape:label="([^"]+)"', SVG_2010.read_text(encoding="utf-8")))

    wb = openpyxl.load_workbook(SOURCE, read_only=True, data_only=True)
    ws = wb["2016"]
    rows = list(ws.iter_rows(values_only=True))
    header = rows[0]
    name_i = header.index("Constituecy")
    leave_i = header.index("Leave Vote")

    records = []
    skipped = []
    for row in rows[1:]:
        raw_name = row[name_i]
        if not raw_name:
            continue
        name = resolve(raw_name, svg_labels)
        if name is None:
            skipped.append(raw_name)
            continue

        leave_share = float(row[leave_i])
        leave = round(leave_share * 1000)
        remain = 1000 - leave

        records.append({
            "Name": name,
            "Electorate": 1000,
            "LEAVE": leave,
            "REMAIN": remain,
            "Total": 1000,
            "Winner": "LEAVE" if leave >= remain else "REMAIN",
        })

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)

    print(f"Wrote {len(records)} constituencies to {OUTPUT}")
    if skipped:
        print(f"Skipped {len(skipped)} rows with no match on the pre-2024 map: {skipped}")


if __name__ == "__main__":
    main()
