"""
Consolidates everything the HTML report artifact needs into one JSON file:
per-nation PCA coordinates (for the scatter), truncated dendrogram geometry,
k-selection curves, cluster profiles, tribe comparison, and top feature/vote
correlations. Run after 01-04.

Writes clustering/output/artifact_data.json

Usage:
    py 05_export_artifact_data.py
"""
import json
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.cluster.hierarchy import dendrogram

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT = BASE_DIR / "output"
NATIONS = ["england", "scotland", "wales"]

# Rank-1..8 segments (by seat count) get a real categorical color in the
# scatter/legend; anything beyond slot 8 is rendered recessively (outline
# only) to avoid cycling hues past the validated categorical palette -
# identity for those is still available via hover/labels.
MAX_COLORED_SEGMENTS = 8


def truncated_dendrogram(nation, max_leaves=24):
    data = json.load(open(OUTPUT / f"dendrogram_{nation}.json", encoding="utf-8"))
    Z = np.array(data["linkage_matrix"])
    ddata = dendrogram(Z, no_plot=True, truncate_mode="lastp", p=max_leaves,
                        labels=data["labels"])
    return {
        "icoord": ddata["icoord"],
        "dcoord": ddata["dcoord"],
        "ivl": ddata["ivl"],  # leaf labels (may be "(n)" for merged clusters)
    }


def build_whole_seat_model():
    diagnostics = json.load(open(OUTPUT / "whole_seat_clusters_diagnostics.json", encoding="utf-8"))
    profiles = json.load(open(OUTPUT / "whole_seat_clusters_profiles.json", encoding="utf-8"))
    tribe_cmp = json.load(open(OUTPUT / "whole_seat_tribe_comparison.json", encoding="utf-8"))
    selection = pd.read_csv(OUTPUT / "whole_seat_model_selection.csv")

    seg = pd.read_csv(OUTPUT / "whole_seat_clusters_demographics.csv")
    pca = pd.read_csv(OUTPUT / "whole_seat_clusters_pca_coords.csv")
    size_rank = {p["segment"]: i + 1 for i, p in enumerate(sorted(profiles, key=lambda p: -p["n_seats"]))}

    seg_membership_cols = [c for c in seg.columns if c.startswith("Segment_")]
    seg_small = seg[["Seat", "Nation", "GMM_label", "DBSCAN_outlier"] + seg_membership_cols]
    merged = pca.merge(seg_small, on="Seat", suffixes=("", "_seg"))

    points = []
    for _, row in merged.iterrows():
        memberships = {c.replace("Segment_", ""): round(float(row[c]), 1) for c in seg_membership_cols}
        points.append({
            "seat": row["Seat"], "nation": row["Nation"],
            "pc1": round(float(row["PC1"]), 3), "pc2": round(float(row["PC2"]), 3),
            "segment": int(row["GMM_label"]), "colorRank": size_rank.get(int(row["GMM_label"]), 99),
            "topMembership": max(memberships.values()), "outlier": bool(row["DBSCAN_outlier"]),
        })

    # model-selection comparison table -> {embedding: {algorithm: {metric: [[k, value], ...]}}}
    curves = {}
    for (emb, algo), grp in selection[selection["algorithm"] != "DBSCAN"].groupby(["embedding", "algorithm"]):
        grp = grp.sort_values("k")
        curves.setdefault(emb, {})[algo] = {
            "k": grp["k"].tolist(),
            "distortion": grp["distortion"].round(2).tolist(),
            "silhouette": grp["silhouette"].round(4).tolist(),
            "davies_bouldin": grp["davies_bouldin"].round(4).tolist(),
            "calinski_harabasz": grp["calinski_harabasz"].round(1).tolist(),
        }

    # every DBSCAN attempt (2 embeddings x 4 density thresholds), degenerate
    # ones (found <2 clusters) included and flagged rather than hidden - it
    # doesn't sweep a k, so it doesn't fit the curve shape above.
    dbscan_rows = []
    for _, r in selection[selection["algorithm"] == "DBSCAN"].sort_values(["embedding", "eps_percentile"]).iterrows():
        dbscan_rows.append({
            "embedding": r["embedding"], "eps_percentile": int(r["eps_percentile"]),
            "n_clusters": int(r["k"]), "n_noise": int(r["n_noise"]), "degenerate": bool(r["degenerate"]),
            "distortion": None if pd.isna(r["distortion"]) else round(float(r["distortion"]), 2),
            "silhouette": None if pd.isna(r["silhouette"]) else round(float(r["silhouette"]), 4),
            "davies_bouldin": None if pd.isna(r["davies_bouldin"]) else round(float(r["davies_bouldin"]), 4),
            "calinski_harabasz": None if pd.isna(r["calinski_harabasz"]) else round(float(r["calinski_harabasz"]), 1),
        })

    return {
        "diagnostics": diagnostics,
        "profiles": profiles,
        "dbscanSweep": dbscan_rows,
        "sizeRank": size_rank,
        "tribeComparison": tribe_cmp,
        "points": points,
        "dendrogram": truncated_dendrogram_from_path(OUTPUT / "whole_seat_clusters_dendrogram.json"),
        "modelSelectionCurves": curves,
    }


def truncated_dendrogram_from_path(path, max_leaves=30):
    data = json.load(open(path, encoding="utf-8"))
    # already truncated at export time (07 script), just pass through
    return {"icoord": data["icoord"], "dcoord": data["dcoord"], "ivl": data["ivl"]}


def top_correlations(corr_df, n=4):
    out = {}
    for (nation, party, target), grp in corr_df.groupby(["Nation", "Party", "Target"]):
        grp = grp.dropna(subset=["Pearson_r"]).sort_values("Pearson_r")
        key = f"{nation}|{party}|{target}"
        out[key] = {
            "top_negative": grp.head(n)[["Feature", "Pearson_r"]].to_dict("records"),
            "top_positive": grp.tail(n)[["Feature", "Pearson_r"]].sort_values(
                "Pearson_r", ascending=False)[["Feature", "Pearson_r"]].to_dict("records"),
        }
    return out


TRIBES = ["Muslim", "Left", "Progressives", "Average", "Liberal", "Blues", "Reforms"]


def build_archetype_model():
    archetypes = json.load(open(OUTPUT / "archetypes.json", encoding="utf-8"))
    membership = pd.read_csv(OUTPUT / "archetype_membership.csv")
    k = archetypes["k"]
    arch_cols = [f"Archetype_{i+1}" for i in range(k)]

    seats = []
    for _, row in membership.iterrows():
        seats.append({
            "seat": row["Seat"],
            "nation": row["Nation"],
            "region": row["Region"],
            "memberships": [round(float(row[c]), 1) for c in arch_cols],
            "handTribes": {t: round(float(row[f"Hand_{t}"]), 1) for t in TRIBES},
            "dominantHandTribe": row["DominantHandTribe"],
        })

    return {
        "k": k,
        "ecologicalR2": archetypes["ecological_r2_2024"],
        "ecologicalR2ByParty": archetypes["ecological_r2_2024_by_party"],
        "kSearchCurve": archetypes["k_search_curve"],
        "nSeats": archetypes["n_seats"],
        "archetypes": archetypes["archetypes"],
        "seats": seats,
    }


def main():
    result = {"nations": {}, "archetypeModel": build_archetype_model(), "wholeSeatModel": build_whole_seat_model()}

    corr_df = pd.read_csv(OUTPUT / "feature_vote_correlations.csv")
    result["top_correlations"] = top_correlations(corr_df)

    with open(OUTPUT / "vote_regressions.json", encoding="utf-8") as f:
        regressions = json.load(f)
    result["regressions"] = regressions

    for nation in NATIONS:
        diagnostics = json.load(open(OUTPUT / f"clustering_diagnostics_{nation}.json", encoding="utf-8"))
        profiles = json.load(open(OUTPUT / f"cluster_profiles_{nation}.json", encoding="utf-8"))
        tribe_cmp = json.load(open(OUTPUT / f"tribe_comparison_{nation}.json", encoding="utf-8"))

        seg = pd.read_csv(OUTPUT / f"segments_{nation}.csv")
        pca = pd.read_csv(OUTPUT / f"pca_coords_{nation}.csv")

        # Segment size rank -> color slot (1..8 colored, 9+ recessive).
        size_rank = {p["segment"]: i + 1 for i, p in enumerate(
            sorted(profiles, key=lambda p: -p["n_seats"]))}

        seg_membership_cols = [c for c in seg.columns if c.startswith("Segment_")]
        seg_small = seg[["Seat", "GMM_label", "DBSCAN_outlier"] + seg_membership_cols]
        merged = pca.merge(seg_small, on="Seat", suffixes=("", "_seg"))

        points = []
        for _, row in merged.iterrows():
            memberships = {c.replace("Segment_", ""): round(float(row[c]), 1) for c in seg_membership_cols}
            top_membership = max(memberships.values())
            points.append({
                "seat": row["Seat"],
                "pc1": round(float(row["PC1"]), 3),
                "pc2": round(float(row["PC2"]), 3),
                "segment": int(row["GMM_label"]),
                "colorRank": size_rank.get(int(row["GMM_label"]), 99),
                "topMembership": top_membership,
                "outlier": bool(row["DBSCAN_outlier"]),
            })

        result["nations"][nation] = {
            "diagnostics": diagnostics,
            "profiles": profiles,
            "sizeRank": size_rank,
            "tribeComparison": tribe_cmp,
            "points": points,
            "dendrogram": truncated_dendrogram(nation),
        }
        print(f"{nation}: {len(points)} points, {len(profiles)} profiles exported")

    out_path = OUTPUT / "artifact_data.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f)
    size_kb = out_path.stat().st_size / 1024
    print(f"Wrote {out_path} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
