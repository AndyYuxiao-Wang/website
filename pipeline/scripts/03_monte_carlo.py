import pandas as pd
import numpy as np
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
INTERMEDIATE = BASE_DIR / "data" / "intermediate"

# -------------------------
# Settings
# -------------------------

INPUT_FILE = INTERMEDIATE / "projected_results.csv"
OUTPUT_FILE = INTERMEDIATE / "seat_probabilities.csv"

SIMULATIONS = 10000
STD_DEV = 0.30

parties = [
    "Labour",
    "Conservative",
    "Reform",
    "Restore",
    "LibDem",
    "Green",
    "Oth",
    "SNP",
    "Plaid",
    "Restore"
]

# -------------------------
# Load projections
# -------------------------

df = pd.read_csv(INPUT_FILE)

# Ensure every party column exists
for p in parties:
    if p not in df.columns:
        df[p] = 0

results = []

# -------------------------
# Monte Carlo
# -------------------------

for i, (_, row) in enumerate(df.iterrows()):

    print(f"{i+1}/{len(df)}")

    wins = {p: 0 for p in parties}

    means = np.array([row[p] for p in parties], dtype=float)

    # Standard deviation proportional to projected vote
    stds = means * STD_DEV

    for _ in range(SIMULATIONS):

        draw = np.random.normal(means, stds)

        # No negative vote shares
        draw = np.clip(draw, 0, None)

        total = draw.sum()

        if total == 0:
            continue

        # Renormalise to 100%
        draw = draw / total * 100

        winner = parties[np.argmax(draw)]
        wins[winner] += 1

    out = {
        "Seat": row["Seat"]
    }

    for p in parties:
        out[p + "_Prob"] = wins[p] / SIMULATIONS

    out["PredictedWinner"] = max(wins, key=wins.get)
    out["WinnerProb"] = max(wins.values()) / SIMULATIONS

    results.append(out)

# -------------------------
# Save
# -------------------------

output = pd.DataFrame(results)

# Alphabetical order
output = output.sort_values("Seat")

output.to_csv(OUTPUT_FILE, index=False)

print(output.head())