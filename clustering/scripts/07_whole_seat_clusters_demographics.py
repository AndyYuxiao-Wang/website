"""
Clusters each of the 632 GB constituencies as a single whole unit, using
ONLY census demographics (no vote share, no swing) - the same PCA + K-Means
+ Ward hierarchical + GMM + DBSCAN approach as 02_run_clustering.py, but:
  - demographics only as features (that script also fed in 2019/2024 vote
    share and swing, which was informative but made the resulting segments
    partly circular with the thing you'd want to explain with them)
  - all three nations pooled into one clustering, not fit separately
  - the actual 2024/2019 vote shares and swing are attached afterwards,
    purely as a descriptive overlay on the resulting clusters (like a
    survey cross-tab) - never used to form the clusters themselves

This sits between the other two analyses in the artifact:
  - 06_archetype_unmixing.py answers "what mixture is this seat made of"
    (every seat is a blend of archetypes, weights sum to 100%)
  - this script answers "which whole seats most resemble each other" - the
    harder question of whether demographics alone actually separate GB
    seats into discrete types, independent of how they happen to vote

Usage:
    py 07_whole_seat_clusters_demographics.py
"""
import json
import numpy as np
import pandas as pd
import openpyxl
from pathlib import Path

from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans, AgglomerativeClustering, DBSCAN
from sklearn.mixture import GaussianMixture
from sklearn.metrics import (
    silhouette_score, adjusted_rand_score,
    davies_bouldin_score, calinski_harabasz_score,
)
from sklearn.neighbors import NearestNeighbors
from scipy.cluster.hierarchy import linkage, dendrogram
import umap

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent
OUTPUT = BASE_DIR / "output"
RANDOM_STATE = 42

DEMOGRAPHICS_XLSX = PROJECT_ROOT / "demographics.xlsx"
RAW_CON = PROJECT_ROOT / "pipeline" / "data" / "raw"
ELECTIONS = PROJECT_ROOT / "web" / "data" / "elections"

DEMOGRAPHIC_COLUMNS = [
    ("Superwealthy", "Superwealthy"), ("LGBT", "LGBT"),
    ("White", "White"), ("White British", "WhiteBritish"), ("White Other", "WhiteOther"),
    ("Asian", "Asian"), ("Indian", "Indian"), ("Pakistani2", "Pakistani"),
    ("Bangladeshi2", "Bangladeshi"), ("Chinese", "Chinese"), ("Black", "Black"),
    ("Arab", "Arab"), ("Mixed", "Mixed"), ("Other Ethnicity", "OtherEthnicity"),
    ("Christian", "Christian"), ("No Religion", "NoReligion"), ("Muslim", "Muslim"),
    ("Hindi", "Hindu"), ("Jewish", "Jewish"), ("Sikh", "Sikh"), ("Bhuddist", "Buddhist"),
    ("Veterans", "Veterans"), ("0 to 17", "Age0to17"), ("18 to 24", "Age18to24"),
    ("65+", "Age65plus"), ("No Qualifications", "NoQualifications"), ("Degrees", "Degrees"),
    ("PublicSector", "PublicSector"), ("Managerial/Professional", "ManagerialProfessional"),
    ("Intermediate", "Intermediate"), ("Routine", "Routine"),
    ("SocialRent", "SocialRent"), ("PrivateRent", "PrivateRent"), ("Owner-Occupation", "OwnerOccupation"),
    # Rural dropped: unpopulated for every Scottish seat in the source workbook.
]
FRACTION_COLUMNS = {clean for _src, clean in DEMOGRAPHIC_COLUMNS} - {"Superwealthy"}

TRIBES = ["Muslim", "Left", "Progressives", "Average", "Liberal", "Blues", "Reforms"]
NATION_FILES = {"england": "englandCon.csv", "scotland": "scotlandCon.csv", "wales": "walesCon.csv"}
ALL_PARTIES = ["LAB", "CON", "REF", "LD", "GRN", "OTHER", "SNP", "PLAID"]


def load_demographics():
    wb = openpyxl.load_workbook(DEMOGRAPHICS_XLSX, read_only=True, data_only=True)
    ws = wb["Demographics"]
    rows = list(ws.iter_rows(values_only=True))
    header = rows[0]
    col_index = {name: i for i, name in enumerate(header)}
    seat_i = col_index["Seat"]

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


def load_nation_and_tribes():
    frames = []
    for nation, fname in NATION_FILES.items():
        df = pd.read_csv(RAW_CON / fname, usecols=["Seat", "County", "Region"] + TRIBES)
        df["Nation"] = nation
        df["DominantHandTribe"] = df[TRIBES].idxmax(axis=1)
        df = df.rename(columns={t: f"Tribe_{t}" for t in TRIBES})
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def load_vote_shares():
    def load(fname, prefix):
        records = json.load(open(ELECTIONS / fname, encoding="utf-8"))
        rows = []
        for r in records:
            total = pd.to_numeric(r.get("Total"), errors="coerce")
            rec = {"Seat": r["Name"]}
            for p in ALL_PARTIES:
                votes = pd.to_numeric(r.get(p), errors="coerce")
                rec[f"{prefix}_{p}"] = (votes / total * 100) if total and total > 0 else np.nan
            rows.append(rec)
        return pd.DataFrame(rows)

    y2019 = load("au2021.json", "y2019")
    y2024 = load("2024.json", "y2024")
    merged = y2019.merge(y2024, on="Seat")
    for p in ALL_PARTIES:
        merged[f"y2019_{p}"] = merged[f"y2019_{p}"].fillna(0)
        merged[f"y2024_{p}"] = merged[f"y2024_{p}"].fillna(0)
        merged[f"swing_{p}"] = merged[f"y2024_{p}"] - merged[f"y2019_{p}"]
    return merged


def pick_kmeans_k(X, k_max):
    scores = {}
    for k in range(2, k_max + 1):
        labels = KMeans(n_clusters=k, n_init=10, random_state=RANDOM_STATE).fit_predict(X)
        scores[k] = silhouette_score(X, labels)
    best_k = max(scores, key=scores.get)
    return best_k, scores


def pick_gmm_k(X, k_max):
    scores = {}
    for k in range(2, k_max + 1):
        gmm = GaussianMixture(n_components=k, covariance_type="diag", random_state=RANDOM_STATE, n_init=12)
        gmm.fit(X)
        scores[k] = gmm.bic(X)
    best_k = min(scores, key=scores.get)
    return best_k, scores


def label_cluster(mean_row, nation_mean, nation_std, top_n=5):
    z = (mean_row - nation_mean) / nation_std.replace(0, np.nan)
    z = z.dropna().sort_values(key=np.abs, ascending=False).head(top_n)
    parts = [f"{'high' if v > 0 else 'low'} {name} (z={v:+.1f})" for name, v in z.items()]
    return "; ".join(parts)


# ---------------------------------------------------------------------
# Model-selection: PCA vs UMAP, K-Means / HAC / GMM across k, DBSCAN
# across a few density thresholds, scored on Distortion, Silhouette,
# Davies-Bouldin and Calinski-Harabasz.
# ---------------------------------------------------------------------

def find_elbow_generic(xs, ys):
    """Point of max perpendicular distance from the chord joining the first
    and last (x, y) point. Works for any roughly-monotonic curve regardless
    of whether it's increasing/decreasing or concave/convex (distortion
    curves fall; silhouette/Calinski-Harabasz peak; Davies-Bouldin dips)."""
    xs = np.array(xs, dtype=float)
    ys = np.array(ys, dtype=float)
    xn = (xs - xs.min()) / (xs.max() - xs.min() + 1e-12)
    yn = (ys - ys.min()) / (ys.max() - ys.min() + 1e-12)
    x1, y1, x2, y2 = xn[0], yn[0], xn[-1], yn[-1]
    dist = np.abs((y2 - y1) * xn - (x2 - x1) * yn + x2 * y1 - y2 * x1) / np.hypot(y2 - y1, x2 - x1)
    return int(xs[np.argmax(dist)])


def distortion(X, labels):
    """Within-cluster sum of squared distances to each cluster's own
    centroid - the generic form of what KMeans calls "inertia", computed
    the same way for any hard partition so it's comparable across algorithms."""
    total = 0.0
    for lab in np.unique(labels):
        pts = X[labels == lab]
        if len(pts) == 0:
            continue
        centroid = pts.mean(axis=0)
        total += float(((pts - centroid) ** 2).sum())
    return total


def evaluate_partition(X, labels):
    """All four requested metrics for one hard partition. DBSCAN noise
    points (label -1) are excluded before scoring, which is standard
    practice for these metrics (they're undefined for a "cluster" of
    scattered unclustered points)."""
    mask = labels != -1
    Xc, labelsc = X[mask], labels[mask]
    n_clusters = len(set(labelsc))
    if n_clusters < 2 or n_clusters >= len(labelsc):
        return None
    return {
        "distortion": distortion(Xc, labelsc),
        "silhouette": float(silhouette_score(Xc, labelsc)),
        "davies_bouldin": float(davies_bouldin_score(Xc, labelsc)),
        "calinski_harabasz": float(calinski_harabasz_score(Xc, labelsc)),
        "n_noise": int((~mask).sum()),
    }


def run_model_selection(embeddings, k_max):
    """embeddings: {name: X_2d_array}. Sweeps K-Means/HAC/GMM across
    k=2..k_max on each embedding, plus DBSCAN at a few density thresholds
    (it has no k), scoring every resulting partition on all four metrics."""
    rows = []
    for emb_name, X in embeddings.items():
        for k in range(2, k_max + 1):
            km_labels = KMeans(n_clusters=k, n_init=10, random_state=RANDOM_STATE).fit_predict(X)
            hac_labels = AgglomerativeClustering(n_clusters=k, linkage="ward").fit_predict(X)
            gmm = GaussianMixture(n_components=k, covariance_type="diag", random_state=RANDOM_STATE, n_init=8)
            gmm_labels = gmm.fit_predict(X)

            for algo, labels in [("KMeans", km_labels), ("HAC", hac_labels), ("GMM", gmm_labels)]:
                m = evaluate_partition(X, labels)
                if m:
                    rows.append({"embedding": emb_name, "algorithm": algo, "k": k, **m})

        min_samples = max(3, X.shape[0] // 60)
        nn = NearestNeighbors(n_neighbors=min_samples).fit(X)
        dists, _ = nn.kneighbors(X)
        for pct in [80, 85, 90, 95]:
            eps = float(np.percentile(dists[:, -1], pct))
            labels = DBSCAN(eps=eps, min_samples=min_samples).fit_predict(X)
            n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
            n_noise = int((labels == -1).sum())
            m = evaluate_partition(X, labels)
            # Record every attempt, even degenerate ones (found <2 clusters) -
            # that's a genuine result ("this density threshold finds no split
            # at all"), not a failure to hide. Metrics are null when there's
            # nothing valid to score.
            row = {"embedding": emb_name, "algorithm": "DBSCAN", "k": n_clusters,
                   "eps_percentile": pct, "n_noise": n_noise,
                   "degenerate": m is None}
            if m:
                row.update(m)
            else:
                row.update({"distortion": None, "silhouette": None,
                            "davies_bouldin": None, "calinski_harabasz": None})
            rows.append(row)
        print(f"  model selection done for embedding={emb_name}")
    return rows


def recommend_k(rows, embedding, algorithm):
    """For one (embedding, algorithm), the per-metric recommended k plus a
    consensus (median) - the four metrics often disagree, so both are
    reported rather than silently picking one."""
    sub = [r for r in rows if r["embedding"] == embedding and r["algorithm"] == algorithm]
    if not sub:
        return None
    ks = [r["k"] for r in sub]
    picks = {
        "distortion": find_elbow_generic(ks, [r["distortion"] for r in sub]),
        "silhouette": ks[int(np.argmax([r["silhouette"] for r in sub]))],
        "davies_bouldin": ks[int(np.argmin([r["davies_bouldin"] for r in sub]))],
        "calinski_harabasz": ks[int(np.argmax([r["calinski_harabasz"] for r in sub]))],
    }
    consensus = int(np.median(list(picks.values())))
    return {"per_metric": picks, "consensus_k": consensus}


def main():
    demo = load_demographics()
    nation_tribes = load_nation_and_tribes()
    votes = load_vote_shares()
    merged = nation_tribes.merge(demo, on="Seat", how="left").merge(votes, on="Seat", how="left")

    feature_cols = [clean for _src, clean in DEMOGRAPHIC_COLUMNS]
    X_raw = merged[feature_cols].to_numpy(dtype=float)
    n_seats = len(merged)
    print(f"Pooled {n_seats} GB seats, {len(feature_cols)} demographic-only features")

    X_scaled = StandardScaler().fit_transform(X_raw)

    pca_full = PCA(random_state=RANDOM_STATE).fit(X_scaled)
    cum_var = np.cumsum(pca_full.explained_variance_ratio_)
    n_components = int(np.searchsorted(cum_var, 0.90) + 1)
    n_components = max(2, min(n_components, n_seats // 10, len(feature_cols)))
    X_pca = PCA(n_components=n_components, random_state=RANDOM_STATE).fit_transform(X_scaled)

    # UMAP at the same target dimensionality as PCA, for a fair side-by-side
    # comparison rather than comparing a high-dim PCA space to a 2D UMAP
    # plot. n_jobs=1 makes it reproducible under a fixed random_state.
    X_umap = umap.UMAP(n_components=n_components, n_neighbors=15, min_dist=0.1,
                        random_state=RANDOM_STATE, n_jobs=1).fit_transform(X_scaled)

    k_max = max(4, min(20, n_seats // 15))
    print(f"PCA: {n_components} components ({cum_var[n_components-1]:.0%} var). "
          f"UMAP: {n_components} components. Searching k=2..{k_max}")

    # --- model selection: PCA vs UMAP x KMeans/HAC/GMM/DBSCAN x 4 metrics ---
    print("Running model selection (Distortion, Silhouette, Davies-Bouldin, Calinski-Harabasz)...")
    selection_rows = run_model_selection({"PCA": X_pca, "UMAP": X_umap}, k_max)
    recommendations = {
        f"{emb}_{algo}": recommend_k(selection_rows, emb, algo)
        for emb in ["PCA", "UMAP"] for algo in ["KMeans", "HAC", "GMM"]
    }
    for name, rec in recommendations.items():
        if rec:
            print(f"  {name}: per-metric k={rec['per_metric']}, consensus k={rec['consensus_k']}")

    # PCA is used for the final model: UMAP explicitly warps inter-point
    # distances to preserve local neighborhoods for visualization, which
    # inflates apparent cluster separation on exactly the metrics being used
    # here (Silhouette/Davies-Bouldin/Calinski-Harabasz all assume the
    # embedding's distances are meaningful) - PCA's distances stay a genuine
    # (linear) read of the original demographic space, which is what these
    # metrics were designed to score. GMM is used for the actual output
    # since it gives soft membership; the consensus k across all four
    # requested metrics, evaluated on GMM's own partitions, sets k.
    best_k_gmm = recommendations["PCA_GMM"]["consensus_k"]
    bic_scores = pick_gmm_k(X_pca, k_max)[1]  # kept for reference/reporting alongside the 4 requested metrics
    gmm = GaussianMixture(n_components=best_k_gmm, covariance_type="diag", random_state=RANDOM_STATE, n_init=12)
    gmm.fit(X_pca)
    gmm_labels = gmm.predict(X_pca)
    gmm_proba = gmm.predict_proba(X_pca)

    best_k_kmeans, silhouette_scores = pick_kmeans_k(X_pca, k_max)
    kmeans_labels = KMeans(n_clusters=best_k_gmm, n_init=10, random_state=RANDOM_STATE).fit_predict(X_pca)

    agg = AgglomerativeClustering(n_clusters=best_k_gmm, linkage="ward")
    agg_labels = agg.fit_predict(X_pca)
    Z = linkage(X_pca, method="ward")

    min_samples = max(3, n_seats // 60)
    nn = NearestNeighbors(n_neighbors=min_samples).fit(X_pca)
    dists, _ = nn.kneighbors(X_pca)
    eps = float(np.percentile(dists[:, -1], 90))
    dbscan_labels = DBSCAN(eps=eps, min_samples=min_samples).fit_predict(X_pca)

    ari_kmeans_gmm = adjusted_rand_score(kmeans_labels, gmm_labels)
    ari_kmeans_agg = adjusted_rand_score(kmeans_labels, agg_labels)
    ari_agg_gmm = adjusted_rand_score(agg_labels, gmm_labels)
    ari_hand_tribe = adjusted_rand_score(merged["DominantHandTribe"], gmm_labels)
    print(f"Working k={best_k_gmm} (BIC). KMeans silhouette-optimal k={best_k_kmeans}. "
          f"ARI(KMeans,GMM)={ari_kmeans_gmm:.2f}, ARI(vs hand tribes)={ari_hand_tribe:.2f}, "
          f"DBSCAN outliers={int((dbscan_labels==-1).sum())}")

    # --- vs hand-built tribes: contingency table + biggest disagreements ---
    tribe_df = pd.DataFrame({"Seat": merged["Seat"], "DominantTribe": merged["DominantHandTribe"],
                              "GMM_label": gmm_labels + 1})
    contingency = pd.crosstab(tribe_df["DominantTribe"], tribe_df["GMM_label"])
    contingency.columns = [f"Segment_{c}" for c in contingency.columns]
    segment_majority_tribe = tribe_df.groupby("GMM_label")["DominantTribe"].agg(lambda s: s.value_counts().idxmax())
    tribe_df["SegmentMajorityTribe"] = tribe_df["GMM_label"].map(segment_majority_tribe)
    disagreements = tribe_df[tribe_df["DominantTribe"] != tribe_df["SegmentMajorityTribe"]]
    tribe_comparison = {
        "adjusted_rand_index": round(float(ari_hand_tribe), 3),
        "n_seats": int(len(tribe_df)), "n_disagreements": int(len(disagreements)),
        "contingency_table": {k: {kk: int(vv) for kk, vv in v.items()} for k, v in contingency.to_dict().items()},
        "disagreement_seats": sorted(
            disagreements[["Seat", "DominantTribe", "GMM_label", "SegmentMajorityTribe"]].to_dict("records"),
            key=lambda r: r["Seat"]),
    }
    with open(OUTPUT / "whole_seat_tribe_comparison.json", "w", encoding="utf-8") as f:
        json.dump(tribe_comparison, f, indent=2, default=lambda o: o.item() if hasattr(o, "item") else o)

    # --- cluster profiles: demographic z-scores + descriptive (not fitted-on) vote overlay ---
    feat_df = pd.DataFrame(X_raw, columns=feature_cols)
    nation_mean, nation_std = feat_df.mean(), feat_df.std(ddof=0)
    y2024_cols = [f"y2024_{p}" for p in ALL_PARTIES]
    swing_cols = [f"swing_{p}" for p in ALL_PARTIES]

    profiles = []
    for k in range(best_k_gmm):
        mask = gmm_labels == k
        grp = merged[mask]
        mean_row = feat_df[mask].mean()
        label = label_cluster(mean_row, nation_mean, nation_std)
        top_2024 = grp[y2024_cols].mean().sort_values(ascending=False).head(2)
        top_swing = grp[swing_cols].mean().idxmax()
        bottom_swing = grp[swing_cols].mean().idxmin()
        profiles.append({
            "segment": k + 1,
            "n_seats": int(mask.sum()),
            "auto_label": label,
            "leading_parties_2024": {c.replace("y2024_", ""): round(float(v), 1) for c, v in top_2024.items()},
            "biggest_positive_swing": {top_swing.replace("swing_", ""): round(float(grp[top_swing].mean()), 2)},
            "biggest_negative_swing": {bottom_swing.replace("swing_", ""): round(float(grp[bottom_swing].mean()), 2)},
            "seats": sorted(grp["Seat"].tolist()),
        })
    profiles.sort(key=lambda p: -p["n_seats"])

    # --- outputs ---
    seg_cols = {f"Segment_{i+1}": gmm_proba[:, i] * 100 for i in range(best_k_gmm)}
    out = pd.DataFrame({
        "Seat": merged["Seat"], "Nation": merged["Nation"], "Region": merged["Region"],
        "KMeans_label": kmeans_labels + 1, "GMM_label": gmm_labels + 1,
        "Agglomerative_label": agg_labels + 1, "DBSCAN_outlier": (dbscan_labels == -1),
        "DominantHandTribe": merged["DominantHandTribe"],
        **seg_cols,
    })
    out.to_csv(OUTPUT / "whole_seat_clusters_demographics.csv", index=False)

    pd.DataFrame(X_pca, columns=[f"PC{i+1}" for i in range(n_components)]) \
        .assign(Seat=merged["Seat"].values, GMM_label=gmm_labels + 1) \
        .to_csv(OUTPUT / "whole_seat_clusters_pca_coords.csv", index=False)

    ddata = dendrogram(Z, no_plot=True, truncate_mode="lastp", p=30, labels=merged["Seat"].tolist())
    with open(OUTPUT / "whole_seat_clusters_dendrogram.json", "w", encoding="utf-8") as f:
        json.dump({"icoord": ddata["icoord"], "dcoord": ddata["dcoord"], "ivl": ddata["ivl"]}, f)

    diagnostics = {
        "n_seats": n_seats, "n_features": len(feature_cols), "n_pca_components": n_components,
        "pca_variance_explained": float(cum_var[n_components - 1]), "k_max_searched": k_max,
        "working_k": best_k_gmm, "gmm_bic_by_k": bic_scores,
        "kmeans_silhouette_best_k": best_k_kmeans, "kmeans_silhouette_by_k": silhouette_scores,
        "ari_kmeans_vs_gmm": ari_kmeans_gmm, "ari_kmeans_vs_agglomerative": ari_kmeans_agg,
        "ari_agglomerative_vs_gmm": ari_agg_gmm, "ari_vs_hand_tribes": ari_hand_tribe,
        "dbscan_n_outliers": int((dbscan_labels == -1).sum()),
        "model_selection_recommendations": recommendations,
        "chosen_config": {"embedding": "PCA", "algorithm": "GMM", "k": best_k_gmm,
                           "reason": "PCA chosen over UMAP because Silhouette/Davies-Bouldin/"
                                     "Calinski-Harabasz all assume the embedding's distances are "
                                     "real; UMAP explicitly warps distances to preserve local "
                                     "neighborhoods, which inflates apparent separation on exactly "
                                     "these metrics. k is the consensus of all four requested "
                                     "metrics evaluated on GMM's own partitions on PCA."},
    }
    with open(OUTPUT / "whole_seat_clusters_diagnostics.json", "w", encoding="utf-8") as f:
        json.dump(diagnostics, f, indent=2)
    with open(OUTPUT / "whole_seat_clusters_profiles.json", "w", encoding="utf-8") as f:
        json.dump(profiles, f, indent=2)
    pd.DataFrame(selection_rows).to_csv(OUTPUT / "whole_seat_model_selection.csv", index=False)

    print(f"\nWorking k={best_k_gmm} clusters:")
    for p in profiles:
        print(f"  Cluster {p['segment']} (n={p['n_seats']}): {p['auto_label']}")
    print(f"\nWrote outputs to {OUTPUT}")


if __name__ == "__main__":
    main()
