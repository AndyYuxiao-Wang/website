"""
Assembles per-nation feature tables (demographics + 2019/2024 vote shares +
swing) for the clustering pipeline. Does not touch pipeline/ or web/ outputs.

Joins, by Seat name (all four sources match 1:1 across 632 GB seats):
  - demographics.xlsx "Demographics" sheet -> ~35 census variables
  - pipeline/data/raw/{england,scotland,wales}Con.csv -> nation/Region/County
  - web/data/elections/au2021.json -> 2019 notional vote counts
  - web/data/elections/2024.json -> 2024 vote counts

Writes clustering/output/features_{nation}.csv (raw, unstandardized values).

Usage:
    py 01_build_features.py
"""
import json
import openpyxl
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent
OUTPUT = BASE_DIR / "output"

DEMOGRAPHICS_XLSX = PROJECT_ROOT / "demographics.xlsx"
RAW_CON = PROJECT_ROOT / "pipeline" / "data" / "raw"
ELECTIONS = PROJECT_ROOT / "web" / "data" / "elections"

# Same clean demographic columns as pipeline/scripts/06_export_demographics.py,
# reused here so the two exports never drift apart.
DEMOGRAPHIC_COLUMNS = [
    ("Superwealthy",           "Superwealthy"),
    ("Rural",                  "Rural"),
    ("LGBT",                   "LGBT"),
    ("White",                  "White"),
    ("White British",          "WhiteBritish"),
    ("White Other",            "WhiteOther"),
    ("Asian",                  "Asian"),
    ("Indian",                 "Indian"),
    ("Pakistani2",             "Pakistani"),
    ("Bangladeshi2",           "Bangladeshi"),
    ("Chinese",                "Chinese"),
    ("Black",                  "Black"),
    ("Arab",                   "Arab"),
    ("Mixed",                  "Mixed"),
    ("Other Ethnicity",        "OtherEthnicity"),
    ("Christian",              "Christian"),
    ("No Religion",            "NoReligion"),
    ("Muslim",                 "Muslim"),
    ("Hindi",                  "Hindu"),
    ("Jewish",                 "Jewish"),
    ("Sikh",                   "Sikh"),
    ("Bhuddist",               "Buddhist"),
    ("Veterans",               "Veterans"),
    ("0 to 17",                "Age0to17"),
    ("18 to 24",               "Age18to24"),
    ("65+",                    "Age65plus"),
    ("No Qualifications",      "NoQualifications"),
    ("Degrees",                "Degrees"),
    ("PublicSector",           "PublicSector"),
    ("Managerial/Professional","ManagerialProfessional"),
    ("Intermediate",           "Intermediate"),
    ("Routine",                "Routine"),
    ("SocialRent",             "SocialRent"),
    ("PrivateRent",            "PrivateRent"),
    ("Owner-Occupation",       "OwnerOccupation"),
]

# Values in the Demographics sheet are fractions (0-1) except Superwealthy
# (already a percentile-ish score) and Rural (0/1 flag) - detected and left
# alone; everything else that looks like a fraction is rescaled to a
# percentage for readability alongside vote shares.
FRACTION_COLUMNS = {clean for src, clean in DEMOGRAPHIC_COLUMNS} - {"Superwealthy", "Rural"}

NATION_FILES = {
    "england": "englandCon.csv",
    "scotland": "scotlandCon.csv",
    "wales": "walesCon.csv",
}

# Parties actually contested per nation (drop the ones that are structurally
# zero outside their home nation).
NATION_PARTIES = {
    "england": ["LAB", "CON", "REF", "LD", "GRN", "OTHER"],
    "scotland": ["LAB", "CON", "REF", "LD", "GRN", "OTHER", "SNP"],
    "wales": ["LAB", "CON", "REF", "LD", "GRN", "OTHER", "PLAID"],
}


def load_demographics():
    wb = openpyxl.load_workbook(DEMOGRAPHICS_XLSX, read_only=True, data_only=True)
    ws = wb["Demographics"]
    rows = list(ws.iter_rows(values_only=True))
    header = rows[0]
    col_index = {name: i for i, name in enumerate(header)}
    seat_i = col_index["Seat"]

    missing = [src for src, _ in DEMOGRAPHIC_COLUMNS if src not in col_index]
    if missing:
        raise SystemExit(f"Demographics sheet missing columns: {missing}")

    records = []
    for row in rows[1:]:
        seat = row[seat_i]
        if not seat:
            continue
        rec = {"Seat": seat}
        for src, clean in DEMOGRAPHIC_COLUMNS:
            val = row[col_index[src]]
            val = val if isinstance(val, (int, float)) else None
            if val is not None and clean in FRACTION_COLUMNS:
                val = val * 100
            rec[clean] = val
        records.append(rec)
    return pd.DataFrame(records)


def load_nation_map():
    frames = []
    for nation, fname in NATION_FILES.items():
        df = pd.read_csv(RAW_CON / fname, usecols=["Seat", "County", "Region"])
        df["Nation"] = nation
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def load_election(fname, parties, prefix):
    records = json.load(open(ELECTIONS / fname, encoding="utf-8"))
    rows = []
    for r in records:
        total = pd.to_numeric(r.get("Total"), errors="coerce")
        electorate = pd.to_numeric(r.get("Electorate"), errors="coerce")
        rec = {"Seat": r["Name"]}
        for p in parties:
            votes = pd.to_numeric(r.get(p), errors="coerce")
            share = (votes / total * 100) if total and total > 0 else None
            rec[f"{prefix}_{p}_share"] = share
        rec[f"{prefix}_Turnout"] = (total / electorate * 100) if electorate and electorate > 0 else None
        rows.append(rec)
    return pd.DataFrame(rows)


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)

    demo = load_demographics()
    nation_map = load_nation_map()

    all_parties = sorted({p for parties in NATION_PARTIES.values() for p in parties})
    au2021 = load_election("au2021.json", all_parties, "y2019")
    e2024 = load_election("2024.json", all_parties, "y2024")

    merged = nation_map.merge(demo, on="Seat", how="left") \
                       .merge(au2021, on="Seat", how="left") \
                       .merge(e2024, on="Seat", how="left")

    missing_demo = merged[merged["WhiteBritish"].isna()]["Seat"].tolist()
    if missing_demo:
        raise SystemExit(f"Seats missing demographics after join: {missing_demo}")

    for nation, parties in NATION_PARTIES.items():
        sub = merged[merged["Nation"] == nation].copy()

        # A blank vote count in the source JSON means the party did not
        # stand in that seat, i.e. a genuine 0% share - not missing data.
        for p in parties:
            sub[f"y2019_{p}_share"] = sub[f"y2019_{p}_share"].fillna(0)
            sub[f"y2024_{p}_share"] = sub[f"y2024_{p}_share"].fillna(0)
            sub[f"swing_{p}"] = sub[f"y2024_{p}_share"] - sub[f"y2019_{p}_share"]

        # Drop party columns not contested in this nation (structural zeros).
        keep_party_cols = []
        for p in all_parties:
            if p in parties:
                keep_party_cols += [f"y2019_{p}_share", f"y2024_{p}_share", f"swing_{p}"]

        demo_cols = [c for _, c in DEMOGRAPHIC_COLUMNS]
        if nation == "scotland":
            # Rural is unpopulated for every Scottish seat in the source
            # workbook - drop rather than cluster on an all-blank column.
            demo_cols = [c for c in demo_cols if c != "Rural"]

        out_cols = ["Seat", "County", "Region"] + demo_cols + \
                   ["y2019_Turnout", "y2024_Turnout"] + \
                   keep_party_cols
        sub = sub[out_cols].sort_values("Seat")

        out_path = OUTPUT / f"features_{nation}.csv"
        sub.to_csv(out_path, index=False)
        print(f"{nation}: {len(sub)} seats -> {out_path}")


if __name__ == "__main__":
    main()
