import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
RAW = BASE_DIR / "data" / "raw"
INTERMEDIATE = BASE_DIR / "data" / "intermediate"

# -----------------------------------
# Tribes
# -----------------------------------

tribes = [
    "Muslim",
    "Left",
    "Progressives",
    "Average",
    "Liberal",
    "Blues",
    "Reforms"
]

# -----------------------------------
# Projection function
# -----------------------------------

def project(alloc_file, flow_file, parties, output_file):

    alloc = pd.read_csv(alloc_file)

    # Load flow matrices
    flows = {}

    for tribe in tribes:

        df = pd.read_excel(
            flow_file,
            sheet_name=tribe,
            index_col=0
        )

        # Keep only the required party rows/columns
        df = df.loc[parties, parties]

        flows[tribe] = df / 100.0

    rows = []

    # ----------------------------
    # Project every tribe
    # ----------------------------

    for _, row in alloc.iterrows():

        seat = row["Seat"]
        tribe = row["Tribe"]

        matrix = flows[tribe]

        projected = {p: 0.0 for p in parties}

        for old_party in parties:

            voters = row.get(old_party, 0)

            if voters == 0:
                continue

            for new_party in parties:

                projected[new_party] += (
                    voters *
                    matrix.loc[old_party, new_party]
                )

        out = {
            "Seat": seat,
            "Tribe": tribe
        }

        out.update(projected)

        rows.append(out)

    tribe_projection = pd.DataFrame(rows)

    projection = (
        tribe_projection
        .groupby("Seat")[parties]
        .sum()
        .reset_index()
    )

    projection.to_csv(output_file, index=False)

    print(f"Finished {output_file}")

    return projection


# -----------------------------------
# England
# -----------------------------------

england = project(
    INTERMEDIATE / "englandAlloc.csv",
    RAW / "englandFlows.xlsx",
    [
        "Labour",
        "Conservative",
        "Reform",
        "LibDem",
        "Green",
        "Oth",
        "SNP",
        "Plaid",
        "Restore"
    ],
    INTERMEDIATE / "englandProjection.csv"
)

# -----------------------------------
# Scotland
# -----------------------------------

scotland = project(
    INTERMEDIATE / "scotlandAlloc.csv",
    RAW / "scotlandFlows.xlsx",
    [
        "Labour",
        "Conservative",
        "Reform",
        "LibDem",
        "Green",
        "Oth",
        "SNP",
        "Plaid",
        "Restore"
    ],
    INTERMEDIATE / "scotlandProjection.csv"
)

# -----------------------------------
# Wales
# -----------------------------------

wales = project(
    INTERMEDIATE / "walesAlloc.csv",
    RAW / "walesFlows.xlsx",
    [
        "Labour",
        "Conservative",
        "Reform",
        "LibDem",
        "Green",
        "Oth",
        "SNP",
        "Plaid",
        "Restore"
    ],
    INTERMEDIATE / "walesProjection.csv"
)

# -----------------------------------
# Standardise party columns
# -----------------------------------

for df in [england, scotland, wales]:
    for p in [
        "Labour","Conservative","Reform","Restore",
        "LibDem","Green","Oth","SNP","Plaid"
    ]:
        if p not in df.columns:
            df[p] = 0

# Common column order
cols = [
    "Seat",
    "Labour",
    "Conservative",
    "Reform",
    "LibDem",
    "Green",
    "Oth",
    "SNP",
    "Plaid",
    "Restore"
]

england = england[cols]
scotland = scotland[cols]
wales = wales[cols]

# -----------------------------------
# Combine into UK projection
# -----------------------------------

uk = pd.concat(
    [england, scotland, wales],
    ignore_index=True
)

uk.to_csv(INTERMEDIATE / "projected_results.csv", index=False)

print("Finished projected_results.csv")