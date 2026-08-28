"""
Runs multiple clustering techniques per nation on the feature tables built
by 01_build_features.py:

  - PCA            dimensionality reduction before clustering + 2D projection
                    for plotting (n_seats is small relative to ~50+ raw
                    features, especially for Scotland/Wales).
  - K-Means         hard-partition baseline; k chosen by max silhouette.
  - Agglomerative   Ward-linkage hierarchical clustering; cross-checks k and
                    gives a dendrogram (taxonomy of segments).
  - GaussianMixture soft/probabilistic clustering; component count chosen by
                    min BIC. predict_proba() is the primary output - the
                    per-seat "% of constituency that is each segment".
  - DBSCAN          density-based outlier diagnostic (not a primary
                    segmentation) - flags seats that don't fit any clean
                    segment and may be worth modelling individually.

Writes, per nation, into clustering/output/:
  segments_{nation}.csv        per-seat hard labels + GMM soft membership %
  clustering_diagnostics_{nation}.json  k-selection curves, ARI, PCA info
  pca_coords_{nation}.csv      2D PCA projection for plotting
  dendrogram_{nation}.json     scipy linkage matrix for plotting

Usage:
    py 02_run_clustering.py
"""
import json
import numpy as np
import pandas as pd
from pathlib import Path

from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans, AgglomerativeClustering, DBSCAN
from sklearn.mixture import GaussianMixture
from sklearn.metrics import silhouette_score, adjusted_rand_score
from scipy.cluster.hierarchy import linkage

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT = BASE_DIR / "output"

NATIONS = ["england", "scotland", "wales"]
RANDOM_STATE = 42


def non_feature_cols(df):
    return {"Seat", "County", "Region"}


def pick_kmeans_k(X, k_max):
    """Silhouette-maximizing k. Reported as a diagnostic (often finds the
    single strongest hard split, e.g. k=2, in continuous social/political
    data where seats form a spectrum rather than tight discrete blobs)."""
    scores = {}
    for k in range(2, k_max + 1):
        labels = KMeans(n_clusters=k, n_init=10, random_state=RANDOM_STATE).fit_predict(X)
        scores[k] = silhouette_score(X, labels)
    best_k = max(scores, key=scores.get)
    return best_k, scores


def pick_gmm_k(X, k_max):
    """BIC-minimizing k, used as the working segmentation size.

    k_max is already floored to keep a plausible minimum sample size per
    component (see run_nation), so the global BIC minimum over the search
    range is used directly rather than a local-minimum heuristic - with
    n this small, the BIC curve is noisy enough that "first local dip"
    ends up chasing single-step noise rather than real structure.
    """
    scores = {}
    for k in range(2, k_max + 1):
        gmm = GaussianMixture(n_components=k, covariance_type="diag",
                               random_state=RANDOM_STATE, n_init=12)
        gmm.fit(X)
        scores[k] = gmm.bic(X)

    best_k = min(scores, key=scores.get)
    return best_k, scores


def run_nation(nation):
    df = pd.read_csv(OUTPUT / f"features_{nation}.csv")
    feature_cols = [c for c in df.columns if c not in non_feature_cols(df)]
    X_raw = df[feature_cols].to_numpy(dtype=float)

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_raw)

    n_seats = len(df)
    # Cap search range so each component/cluster keeps a plausible minimum
    # sample size (~5 seats), with an absolute ceiling so segments stay
    # human-interpretable regardless of nation size.
    k_max = max(4, min(20, n_seats // 5))

    # PCA: keep enough components for 90% variance, capped so we don't
    # overfit noise on the smaller nations.
    pca_full = PCA(random_state=RANDOM_STATE).fit(X_scaled)
    cum_var = np.cumsum(pca_full.explained_variance_ratio_)
    n_components = int(np.searchsorted(cum_var, 0.90) + 1)
    n_components = max(2, min(n_components, n_seats // 5, len(feature_cols)))
    pca = PCA(n_components=n_components, random_state=RANDOM_STATE)
    X_pca = pca.fit_transform(X_scaled)

    # --- Gaussian Mixture (primary: chooses the working k, soft membership) ---
    best_k_gmm, bic_scores = pick_gmm_k(X_pca, k_max)
    gmm = GaussianMixture(n_components=best_k_gmm, covariance_type="diag",
                           random_state=RANDOM_STATE, n_init=12)
    gmm.fit(X_pca)
    gmm_labels = gmm.predict(X_pca)
    gmm_proba = gmm.predict_proba(X_pca)  # (n_seats, best_k_gmm), rows sum to 1

    # --- K-Means, both at its own silhouette-optimal k (diagnostic - often
    # the single strongest hard split) and at GMM's working k (so the two
    # techniques can be compared like-for-like) ---
    best_k_kmeans, silhouette_scores = pick_kmeans_k(X_pca, k_max)
    kmeans_labels = KMeans(n_clusters=best_k_gmm, n_init=10,
                            random_state=RANDOM_STATE).fit_predict(X_pca)

    # --- Agglomerative (Ward), also at GMM's working k ---
    agg = AgglomerativeClustering(n_clusters=best_k_gmm, linkage="ward")
    agg_labels = agg.fit_predict(X_pca)
    Z = linkage(X_pca, method="ward")

    # --- DBSCAN (outlier diagnostic only) ---
    # eps set from the 90th percentile of k-NN distance in PCA space: the
    # median (standard rule-of-thumb) flags ~40% of seats as noise here,
    # because political/demographic space is a continuum with essentially
    # one connected density blob rather than separated islands - using the
    # median just draws the noise/core line through the middle of that
    # blob. The 90th percentile instead surfaces genuine density outliers
    # (seats sitting well outside the main mass) without mislabelling
    # ordinary seats as anomalous.
    from sklearn.neighbors import NearestNeighbors
    min_samples = max(3, n_seats // 40)
    nn = NearestNeighbors(n_neighbors=min_samples).fit(X_pca)
    dists, _ = nn.kneighbors(X_pca)
    eps = float(np.percentile(dists[:, -1], 90))
    dbscan = DBSCAN(eps=eps, min_samples=min_samples)
    dbscan_labels = dbscan.fit_predict(X_pca)

    # --- Agreement between techniques ---
    ari_kmeans_gmm = adjusted_rand_score(kmeans_labels, gmm_labels)
    ari_kmeans_agg = adjusted_rand_score(kmeans_labels, agg_labels)
    ari_agg_gmm = adjusted_rand_score(agg_labels, gmm_labels)

    # --- Assemble outputs ---
    seg_cols = {f"Segment_{i+1}": gmm_proba[:, i] * 100 for i in range(best_k_gmm)}
    out = pd.DataFrame({
        "Seat": df["Seat"],
        "County": df["County"],
        "Region": df["Region"],
        "KMeans_label": kmeans_labels + 1,
        "GMM_label": gmm_labels + 1,
        "Agglomerative_label": agg_labels + 1,
        "DBSCAN_outlier": (dbscan_labels == -1),
        **seg_cols,
    })
    out.to_csv(OUTPUT / f"segments_{nation}.csv", index=False)

    pd.DataFrame(X_pca, columns=[f"PC{i+1}" for i in range(n_components)]) \
        .assign(Seat=df["Seat"].values, GMM_label=gmm_labels + 1, KMeans_label=kmeans_labels + 1) \
        .to_csv(OUTPUT / f"pca_coords_{nation}.csv", index=False)

    with open(OUTPUT / f"dendrogram_{nation}.json", "w", encoding="utf-8") as f:
        json.dump({
            "labels": df["Seat"].tolist(),
            "linkage_matrix": Z.tolist(),
        }, f)

    diagnostics = {
        "nation": nation,
        "n_seats": n_seats,
        "n_features": len(feature_cols),
        "n_pca_components": n_components,
        "pca_variance_explained": float(cum_var[n_components - 1]),
        "k_max_searched": k_max,
        "working_k": best_k_gmm,
        "gmm_best_k": best_k_gmm,
        "gmm_bic_by_k": bic_scores,
        "kmeans_silhouette_best_k": best_k_kmeans,
        "kmeans_silhouette_by_k": silhouette_scores,
        "note": "kmeans_silhouette_best_k is a diagnostic (the single strongest "
                "hard split); KMeans_label/Agglomerative_label in segments_*.csv "
                "are both computed at the GMM working_k for a like-for-like "
                "comparison, not at kmeans_silhouette_best_k.",
        "ari_kmeans_vs_gmm_at_working_k": ari_kmeans_gmm,
        "ari_kmeans_vs_agglomerative_at_working_k": ari_kmeans_agg,
        "ari_agglomerative_vs_gmm_at_working_k": ari_agg_gmm,
        "dbscan_eps": eps,
        "dbscan_min_samples": min_samples,
        "dbscan_n_outliers": int((dbscan_labels == -1).sum()),
    }
    with open(OUTPUT / f"clustering_diagnostics_{nation}.json", "w", encoding="utf-8") as f:
        json.dump(diagnostics, f, indent=2)

    print(f"{nation}: n={n_seats}, PCA components={n_components} ({cum_var[n_components-1]:.0%} var), "
          f"working k (GMM/BIC)={best_k_gmm}, KMeans silhouette-optimal k={best_k_kmeans}, "
          f"ARI(KMeans,GMM)@working_k={ari_kmeans_gmm:.2f}, DBSCAN outliers={diagnostics['dbscan_n_outliers']}")


def main():
    for nation in NATIONS:
        run_nation(nation)


if __name__ == "__main__":
    main()
