import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
RAW = BASE_DIR / "data" / "raw"
INTERMEDIATE = BASE_DIR / "data" / "intermediate"

# ---------------------------------
# Tribe names
# ---------------------------------

tribes = [
    "Muslim",
    "Left",
    "Progressives",
    "Average",
    "Liberal",
    "Blues",
    "Reforms"
]

# ---------------------------------
# Preferences
# Use None instead of 0
# ---------------------------------

england_preferences = {
    "Muslim": ["Oth","Green","Labour",None,None,"LibDem","Conservative","Reform",None,None],
    "Left": ["Green",None,None,"LibDem","Labour","Oth",None,"Conservative","Reform",None],
    "Progressives": ["Labour","LibDem","Green",None,"Conservative",None,None,None,"Oth","Reform"],
    "Average": [None,"Labour","LibDem","Conservative","Reform",None,"Oth","Green",None,None],
    "Liberal": ["LibDem",None,"Conservative","Labour","Green",None,"Reform",None,None,"Oth"],
    "Blues": ["Conservative",None,None,None,"LibDem","Reform",None,"Oth","Labour","Green"],
    "Reforms": ["Reform","Conservative",None,"Oth",None,None,"LibDem","Labour","Green",None]
}

scotland_preferences = {
    "Muslim": ["SNP","Green","Oth","Labour","LibDem",None,"Reform","Conservative",None,None],
    "Left": [None,"SNP","Green",None,"Labour","Oth","LibDem",None,"Reform","Conservative"],
    "Progressives": ["Labour","LibDem",None,"Green",None,"SNP","Conservative","Reform",None,"Oth"],
    "Average": [None,"Labour","LibDem",None,"SNP","Conservative","Green","Oth",None,"Reform"],
    "Liberal": ["LibDem",None,"Labour","Conservative","Oth","Reform",None,"Green","SNP",None],
    "Blues": ["Conservative",None,None,"LibDem","Reform","Green","Labour",None,"Oth","SNP"],
    "Reforms": ["Reform","Conservative",None,None,None,"Labour","Oth","SNP","Green","LibDem"]
}

wales_preferences = {
    "Muslim": ["Green","Plaid","Oth","Labour",None,"LibDem","Conservative",None,"Reform",None],
    "Left": ["Plaid","Labour",None,"Green","LibDem","Oth",None,"Reform",None,"Conservative"],
    "Progressives": ["Labour","LibDem","Green","Plaid","Conservative",None,None,None,"Oth","Reform"],
    "Average": [None,None,"Labour","Reform","Plaid",None,"Oth","Green","LibDem","Oth"],
    "Liberal": ["LibDem","Oth","Conservative",None,"Labour",None,"Reform",None,"Green","Plaid"],
    "Blues": ["Conservative","Reform","LibDem",None,None,"Labour",None,"Oth","Plaid","Green"],
    "Reforms": ["Reform","Conservative",None,None,"Oth","Plaid","Labour","Green",None,"LibDem"]
}


# ---------------------------------
# Allocation function
# ---------------------------------

def allocate(input_csv, output_csv, preferences, parties):

    df = pd.read_csv(input_csv)

    numeric_cols = tribes + parties

    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    results = []

    for _, row in df.iterrows():

        tribe_remaining = {t: row[t] for t in tribes}
        votes_remaining = {p: row[p] for p in parties}

        allocation = {
            t: {p: 0 for p in parties}
            for t in tribes
        }

        for rnd in range(10):

            for tribe in tribes:

                if tribe_remaining[tribe] <= 0:
                    continue

                party = preferences[tribe][rnd]

                if party is None:
                    continue

                if party not in votes_remaining:
                    continue

                if votes_remaining[party] <= 0:
                    continue

                amount = min(
                    tribe_remaining[tribe],
                    votes_remaining[party]
                )

                allocation[tribe][party] += amount
                tribe_remaining[tribe] -= amount
                votes_remaining[party] -= amount

        for tribe in tribes:

            out = {
                "Seat": row["Seat"],
                "Tribe": tribe
            }

            for p in parties:
                out[p] = allocation[tribe][p]

            results.append(out)

    pd.DataFrame(results).to_csv(output_csv, index=False)
    print(f"Finished {output_csv}")


# ---------------------------------
# Run England
# ---------------------------------

allocate(
    RAW / "englandCon.csv",
    INTERMEDIATE / "englandAlloc.csv",
    england_preferences,
    [
        "Labour","Conservative","Reform",
        "LibDem","Green","Oth","SNP","Plaid"
    ]
)

# ---------------------------------
# Run Scotland
# ---------------------------------

allocate(
    RAW / "scotlandCon.csv",
    INTERMEDIATE / "scotlandAlloc.csv",
    scotland_preferences,
    [
        "Labour","Conservative","Reform",
        "LibDem","Green","Oth","SNP","Plaid"
    ]
)

# ---------------------------------
# Run Wales
# ---------------------------------

allocate(
    RAW / "walesCon.csv",
    INTERMEDIATE / "walesAlloc.csv",
    wales_preferences,
    [
        "Labour","Conservative","Reform",
        "LibDem","Green","Oth","Plaid","Plaid"
    ]
)

print("All three nations completed.")