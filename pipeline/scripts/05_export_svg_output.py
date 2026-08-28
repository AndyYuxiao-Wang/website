import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
RAW = BASE_DIR / "data" / "raw"
INTERMEDIATE = BASE_DIR / "data" / "intermediate"
OUTPUT = BASE_DIR / "data" / "output"
WEB_ELECTIONS = BASE_DIR.parent / "web" / "data" / "elections"

# Load projected percentages
proj = pd.read_csv(INTERMEDIATE / "projected_results_tactical.csv")
local_flows = RAW / "LocalFlows.xlsx"

parties = [
    "Labour",
    "Conservative",
    "Reform",
    "Restore",
    "LibDem",
    "Green",
    "Oth",
    "SNP",
    "Plaid"
]

adjusted_rows = []

for _, row in proj.iterrows():

    seat = row["Seat"]

    # Start with zero projected vote
    new_votes = {p: 0.0 for p in parties}

    try:
        matrix = pd.read_excel(
            local_flows,
            sheet_name=seat,
            index_col=0
        )

        matrix = matrix.loc[parties, parties] / 100.0

    except Exception:
        # No local sheet -> leave unchanged
        adjusted_rows.append(row.to_dict())
        continue

    # Apply local transition matrix
    for old_party in parties:

        voters = row[old_party]

        if voters == 0:
            continue

        for new_party in parties:

            new_votes[new_party] += (
                voters *
                matrix.loc[old_party, new_party]
            )

    out = {"Seat": seat}

    out.update(new_votes)

    adjusted_rows.append(out)

proj = pd.DataFrame(adjusted_rows)
# Load previous turnout
prev = pd.read_excel(
    RAW / "Tactical.xlsx",
    sheet_name="VoteTotals"
)

# Merge
df = proj.merge(prev, on="Seat", how="left")

final = pd.DataFrame()

final["Check"] = df["Seat"]
final["Name"] = df["Seat"]
final["Electorate"] = df["prev_Electorate"]

# ---------------------------------------
# Convert percentages -> votes
# ---------------------------------------

mapping = {
    "Labour": "LAB",
    "Conservative": "CON",
    "Reform": "REF",
    "Restore": "RESTORE",
    "LibDem": "LD",
    "Green": "GRN",
    "Oth": "OTHER",
    "SNP": "SNP",
    "Plaid": "PLAID"
}

for old, new in mapping.items():
    final[new] = (
        df[old] * df["prev_TOTAL"] / 100
    ).round().astype(int)

# ---------------------------------------
# Empty columns required by SVG format
# ---------------------------------------

final["OTH"] = ""
final["UKIP"] = ""
final["BNP"] = ""
final["RES"] = ""

# ---------------------------------------
# Total votes
# ---------------------------------------

vote_cols = [
    "LAB",
    "CON",
    "REF",
    "RESTORE",
    "LD",
    "GRN",
    "OTHER",
    "SNP",
    "PLAID"
]

final["Total"] = final[vote_cols].sum(axis=1)

# ---------------------------------------
# Winner
# ---------------------------------------

party_names = {c: c for c in vote_cols}

final["Winner"] = (
    final[vote_cols]
        .idxmax(axis=1)
        .map(party_names)
)

# ---------------------------------------
# Previous results
# ---------------------------------------

prev_cols = [
    "prev_Electorate",
    "prev_LAB",
    "prev_CON",
    "prev_REF",
    "prev_RESTORE",      # NEW
    "prev_LD",
    "prev_GRN",
    "prev_OTHER",
    "prev_SNP",
    "prev_PLAID",
    "prev_OTH",
    "prev_UKIP",
    "prev_BNP",
    "prev_RES",
    "prev_TOTAL"
]

# If the column doesn't exist yet, create it
if "prev_RESTORE" not in df.columns:
    df["prev_RESTORE"] = 0

for c in prev_cols:
    final[c] = df[c]

# ---------------------------------------
# Alphabetical
# ---------------------------------------

final = final.sort_values("Name")

# ---------------------------------------
# Save
# ---------------------------------------

OUTPUT.mkdir(parents=True, exist_ok=True)

final.to_csv(OUTPUT / "SVG_Output.csv", index=False)

final.to_json(
    OUTPUT / "SVG_Output.json",
    orient="records",
    indent=4
)

# Also drop a copy straight into the web app's "Prediction" dataset,
# so the map picks up a new pipeline run without a manual copy/paste.
if WEB_ELECTIONS.is_dir():
    final.to_json(
        WEB_ELECTIONS / "2029.json",
        orient="records",
        indent=2
    )
    print(f"Also updated {WEB_ELECTIONS / '2029.json'}")

print("Finished SVG_Output.csv and SVG_Output.json")