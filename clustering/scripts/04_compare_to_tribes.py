"""
Compares the empirically-derived GMM segments against the existing
hand-built tribes (Muslim/Left/Progressives/Average/Liberal/Blues/Reforms
from pipeline/data/raw/{nation}Con.csv) - purely as a validation benchmark,
never as a clustering input.

For each seat, takes its dominant hand-built tribe (highest %) and its
dominant empirical GMM segment, and reports:
  - a contingency table per nation (how the two segmentations line up)
  - Adjusted Rand Index (0 = no better than random, 1 = identical partitions)
  - the seats where the two disagree most starkly (biggest "surprises")

Writes clustering/output/tribe_comparison_{nation}.json and
clustering/output/tribe_comparison_summary.csv

Usage:
    py 04_compare_to_tribes.py
"""
import json
import pandas as pd
from pathlib import Path
from sklearn.metrics import adjusted_rand_score

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent
OUTPUT = BASE_DIR / "output"
RAW_CON = PROJECT_ROOT / "pipeline" / "data" / "raw"

NATION_FILES = {
    "england": "englandCon.csv",
    "scotland": "scotlandCon.csv",
    "wales": "walesCon.csv",
}

TRIBES = ["Muslim", "Left", "Progressives", "Average", "Liberal", "Blues", "Reforms"]


def to_native(o):
    """json.dump default= hook for numpy scalar types (int64/float64)."""
    if hasattr(o, "item"):
        return o.item()
    raise TypeError(f"Not JSON serializable: {o!r}")


def main():
    summary_rows = []

    for nation, fname in NATION_FILES.items():
        tribes_df = pd.read_csv(RAW_CON / fname, usecols=["Seat"] + TRIBES)
        tribes_df["DominantTribe"] = tribes_df[TRIBES].idxmax(axis=1)

        seg = pd.read_csv(OUTPUT / f"segments_{nation}.csv")
        merged = seg.merge(tribes_df[["Seat", "DominantTribe"]], on="Seat")

        ari = adjusted_rand_score(merged["DominantTribe"], merged["GMM_label"])

        contingency = pd.crosstab(merged["DominantTribe"], merged["GMM_label"])
        contingency.columns = [f"Segment_{c}" for c in contingency.columns]

        # Biggest "surprises": seats where the empirical segment's own
        # profile makeup is dominated by a *different* tribe than the one
        # the hand-built model assigned it to - approximated here by seats
        # whose empirical segment is, nation-wide, mostly a different tribe.
        segment_majority_tribe = (
            merged.groupby("GMM_label")["DominantTribe"]
            .agg(lambda s: s.value_counts().idxmax())
        )
        merged["SegmentMajorityTribe"] = merged["GMM_label"].map(segment_majority_tribe)
        disagreements = merged[merged["DominantTribe"] != merged["SegmentMajorityTribe"]]

        result = {
            "nation": nation,
            "adjusted_rand_index": round(float(ari), 3),
            "n_seats": int(len(merged)),
            "n_disagreements": int(len(disagreements)),
            "contingency_table": contingency.to_dict(),
            "disagreement_seats": sorted(
                disagreements[["Seat", "DominantTribe", "GMM_label", "SegmentMajorityTribe"]]
                .to_dict("records"),
                key=lambda r: r["Seat"],
            ),
        }
        with open(OUTPUT / f"tribe_comparison_{nation}.json", "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, default=to_native)

        summary_rows.append({
            "Nation": nation, "ARI": result["adjusted_rand_index"],
            "n_seats": result["n_seats"], "n_disagreements": result["n_disagreements"],
        })

        print(f"{nation}: ARI={ari:.3f} vs hand-built tribes, "
              f"{len(disagreements)}/{len(merged)} seats land in a segment "
              f"whose majority tribe differs from their own dominant tribe")

    pd.DataFrame(summary_rows).to_csv(OUTPUT / "tribe_comparison_summary.csv", index=False)


if __name__ == "__main__":
    main()
