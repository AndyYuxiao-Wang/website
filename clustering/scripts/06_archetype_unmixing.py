"""
Reverse-engineers the hand-built tribe percentages properly: instead of
clustering whole constituencies against each other (treating each seat as
one indivisible point - see 02_run_clustering.py), this decomposes each
seat's own census composition into a mixture of K archetypal demographic
profiles whose weights sum to 100% - matching exactly what the hand-built
Muslim/Left/Progressives/Average/Liberal/Blues/Reforms columns are (they
sum to 100% per seat too; verified directly against
pipeline/data/raw/englandCon.csv).

Method (standard in spectral/hyperspectral "unmixing", applied here to
census composition instead of pixel spectra):
  1. NMF discovers K non-negative archetype demographic profiles (the
     "endmembers") that best reconstruct every seat's raw census
     percentages as an additive combination.
  2. Each seat's exact mixture weights are then re-solved under a hard
     sum-to-100% constraint (fully-constrained least squares unmixing:
     append a large-weight constraint row to the regression, solve via
     NNLS, then renormalize) - NMF's own output isn't constrained to sum
     to 1, so this second step is what actually produces "how much of
     this constituency is archetype k" as a true percentage breakdown.
  3. Ecological regression (NNLS per party) then estimates each
     archetype's own implied party vote shares from the actual 2024
     results across all 632 seats and their composition weights - a
     data-driven analogue of the hand-picked preference-order tables in
     pipeline/scripts/01_allocate_tribes.py.

All 632 GB seats are pooled together (England, Scotland, Wales) - since
this step uses demographics only, there's no reason to fit separately per
nation; SNP/Plaid still show up correctly as ~0% everywhere outside their
home nation in the vote data used for the regression step.

Usage:
    py 06_archetype_unmixing.py
"""
import json
import numpy as np
import pandas as pd
import openpyxl
from pathlib import Path
from scipy.optimize import nnls

from sklearn.decomposition import NMF, PCA
from sklearn.preprocessing import StandardScaler

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent
OUTPUT = BASE_DIR / "output"

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
    # Rural is dropped: unpopulated for every Scottish seat in the source
    # workbook, and this run pools all three nations together.
]
FRACTION_COLUMNS = {clean for _src, clean in DEMOGRAPHIC_COLUMNS} - {"Superwealthy"}

ALL_PARTIES = ["LAB", "CON", "REF", "LD", "GRN", "OTHER", "SNP", "PLAID"]

TRIBES = ["Muslim", "Left", "Progressives", "Average", "Liberal", "Blues", "Reforms"]
NATION_FILES = {"england": "englandCon.csv", "scotland": "scotlandCon.csv", "wales": "walesCon.csv"}


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
        # "Muslim" clashes with the religion-demographic column of the same
        # name once merged - rename the hand-tribe columns to keep them apart.
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


def find_elbow(ks, scores):
    """Kneedle-style elbow: point of max perpendicular distance from the
    chord connecting the first and last (k, score) point, on a concave
    increasing curve (here, reconstruction R^2 vs number of archetypes)."""
    ks = np.array(ks, dtype=float)
    scores = np.array(scores, dtype=float)
    kn = (ks - ks.min()) / (ks.max() - ks.min())
    sn = (scores - scores.min()) / (scores.max() - scores.min() + 1e-12)
    x1, y1, x2, y2 = kn[0], sn[0], kn[-1], sn[-1]
    dist = np.abs((y2 - y1) * kn - (x2 - x1) * sn + x2 * y1 - y2 * x1) / np.hypot(y2 - y1, x2 - x1)
    return int(ks[np.argmax(dist)])


def fclsu(x_row, H, delta=300.0):
    """Fully-constrained least-squares unmixing for one seat: solve
    w = argmin ||x - H^T w||^2 s.t. w >= 0, sum(w) ~= 1, via the standard
    augmented-NNLS trick (append a constraint row scaled by delta), then
    hard-renormalize so the output is an exact percentage breakdown."""
    K = H.shape[0]
    A = np.vstack([H.T, np.full((1, K), delta)])
    b = np.append(x_row, delta)
    w, _ = nnls(A, b)
    total = w.sum()
    if total <= 0:
        return np.full(K, 1.0 / K)
    return w / total


def label_archetype(h_row, feature_names, nation_mean, nation_std, top_n=5):
    z = (h_row - nation_mean) / nation_std.replace(0, np.nan)
    z = z.dropna().sort_values(key=np.abs, ascending=False).head(top_n)
    parts = [f"{'high' if v > 0 else 'low'} {name} (z={v:+.1f})" for name, v in z.items()]
    return "; ".join(parts)


def ecological_regression(W, vote_df, targets):
    """NNLS per target: vote_target ~= W @ v, giving each archetype's own
    implied vote outcome, estimated from all 632 seats' actual results
    weighted by how much of each seat's composition is that archetype."""
    results = {}
    K = W.shape[1]
    for col in targets:
        y = vote_df[col].to_numpy(float)
        if y.min() < 0:  # swing can be negative - NNLS doesn't apply, use plain least squares
            v, *_ = np.linalg.lstsq(W, y, rcond=None)
        else:
            v, _ = nnls(W, y)
        results[col] = v.tolist()
    return results


def main():
    demo = load_demographics()
    nation_tribes = load_nation_and_tribes()
    votes = load_vote_shares()

    merged = nation_tribes.merge(demo, on="Seat", how="left").merge(votes, on="Seat", how="left")
    feature_cols = [clean for _src, clean in DEMOGRAPHIC_COLUMNS]
    X = merged[feature_cols].to_numpy(dtype=float)
    n_seats = X.shape[0]
    print(f"Pooled {n_seats} GB seats, {len(feature_cols)} demographic features")

    # NMF's reconstruction objective is scale-sensitive (like PCA/k-means):
    # unscaled, high-magnitude columns (White% swinging 20-99) would dominate
    # the fit and drown out low-magnitude-but-salient ones (Muslim% mostly
    # 0-10, Jewish%, Sikh% etc). Divide each column by its own std first so
    # every feature contributes comparably; NMF still only ever sees
    # non-negative values since std > 0. H is converted back to real
    # percentage units for display/labeling further down.
    col_std = X.std(axis=0)
    col_std[col_std == 0] = 1.0
    Xs = X / col_std

    # --- how many archetypes does the data actually support? ---
    pca = PCA(random_state=42).fit(StandardScaler().fit_transform(X))
    cum_var = np.cumsum(pca.explained_variance_ratio_)
    k_max = int(np.searchsorted(cum_var, 0.93) + 1)
    k_max = max(8, min(20, k_max))
    print(f"Searching k=2..{k_max} (intrinsic dimensionality suggests ~{np.searchsorted(cum_var, 0.90)+1} dims)")

    col_mean_s = Xs.mean(axis=0, keepdims=True)
    total_var = np.linalg.norm(Xs - col_mean_s) ** 2  # proper per-feature-centered R^2 baseline
    ks, r2s = [], []
    for k in range(2, k_max + 1):
        nmf = NMF(n_components=k, init="nndsvda", random_state=42, max_iter=1000)
        Ws0 = nmf.fit_transform(Xs)
        Hs0 = nmf.components_
        recon_err = np.linalg.norm(Xs - Ws0 @ Hs0) ** 2
        r2 = 1 - recon_err / total_var
        ks.append(k)
        r2s.append(r2)
    best_k = find_elbow(ks, r2s)
    print(f"NMF reconstruction R^2 by k: {dict(zip(ks, [round(r,3) for r in r2s]))}")
    print(f"Elbow at k={best_k}")

    # --- fit final NMF at chosen k (nndsvda: deterministic, well-scaled -
    # random inits were found to occasionally converge to a degenerate,
    # badly-scaled H that broke the FCLSU step below) ---
    nmf = NMF(n_components=best_k, init="nndsvda", random_state=42, max_iter=2000)
    nmf.fit_transform(Xs)
    Hs = nmf.components_  # (K, D), in std-scaled units
    H = Hs * col_std  # back to real percentage units for display

    # --- re-solve exact per-seat composition under sum-to-100% constraint,
    # in the same scaled space the archetypes were fit in ---
    row_norm = np.linalg.norm(Hs, axis=1).mean()
    delta = 1.5 * row_norm
    W = np.array([fclsu(Xs[i], Hs, delta=delta) for i in range(n_seats)])  # rows sum to 1
    print(f"FCLSU delta={delta:.2f} (1.5x mean archetype-profile norm {row_norm:.2f})")

    # --- label archetypes from their demographic profile ---
    feat_df = pd.DataFrame(X, columns=feature_cols)
    nation_mean, nation_std = feat_df.mean(), feat_df.std(ddof=0)
    labels = [label_archetype(pd.Series(H[k], index=feature_cols), feature_cols, nation_mean, nation_std)
               for k in range(best_k)]

    # --- ecological regression: each archetype's implied vote profile ---
    vote_targets = [f"y2024_{p}" for p in ALL_PARTIES] + [f"y2019_{p}" for p in ALL_PARTIES] + \
                   [f"swing_{p}" for p in ALL_PARTIES]
    vote_df = merged[vote_targets]
    implied = ecological_regression(W, vote_df, vote_targets)
    pred_y2024 = W @ np.array([implied[f"y2024_{p}"] for p in ALL_PARTIES]).T
    actual_y2024 = merged[[f"y2024_{p}" for p in ALL_PARTIES]].to_numpy(float)
    ss_res = np.sum((actual_y2024 - pred_y2024) ** 2)
    ss_tot = np.sum((actual_y2024 - actual_y2024.mean(axis=0)) ** 2)
    ecological_r2 = 1 - ss_res / ss_tot
    per_party_r2 = {}
    for i, p in enumerate(ALL_PARTIES):
        ss_res_p = np.sum((actual_y2024[:, i] - pred_y2024[:, i]) ** 2)
        ss_tot_p = np.sum((actual_y2024[:, i] - actual_y2024[:, i].mean()) ** 2)
        per_party_r2[p] = round(float(1 - ss_res_p / ss_tot_p), 3) if ss_tot_p > 0 else None
    print(f"Ecological regression R^2 (2024 vote share, all parties pooled): {ecological_r2:.3f}")
    print(f"Per-party R^2: {per_party_r2}")

    # --- assemble outputs ---
    membership_cols = {f"Archetype_{k+1}": W[:, k] * 100 for k in range(best_k)}
    membership = pd.DataFrame({
        "Seat": merged["Seat"], "Nation": merged["Nation"], "County": merged["County"],
        "Region": merged["Region"], "DominantHandTribe": merged["DominantHandTribe"],
        **membership_cols,
    })
    # also carry the hand-built tribe percentages alongside, for direct comparison
    for t in TRIBES:
        membership[f"Hand_{t}"] = merged[f"Tribe_{t}"].to_numpy()
    membership.to_csv(OUTPUT / "archetype_membership.csv", index=False)

    archetypes = []
    dominant_seats = pd.Series(W.argmax(axis=1))
    for k in range(best_k):
        n_dominant = int((dominant_seats == k).sum())
        archetypes.append({
            "archetype": k + 1,
            "label": labels[k],
            "avg_share_of_gb": round(float(W[:, k].mean() * 100), 2),
            "n_seats_dominant": n_dominant,
            "profile": {name: round(float(v), 2) for name, v in zip(feature_cols, H[k])},
            "implied_vote_2024": {p: round(float(implied[f"y2024_{p}"][k]), 1) for p in ALL_PARTIES},
            "implied_vote_2019": {p: round(float(implied[f"y2019_{p}"][k]), 1) for p in ALL_PARTIES},
            "implied_swing": {p: round(float(implied[f"swing_{p}"][k]), 1) for p in ALL_PARTIES},
        })

    with open(OUTPUT / "archetypes.json", "w", encoding="utf-8") as f:
        json.dump({
            "k": best_k,
            "k_search_curve": {str(k): round(r, 4) for k, r in zip(ks, r2s)},
            "ecological_r2_2024": round(float(ecological_r2), 3),
            "ecological_r2_2024_by_party": per_party_r2,
            "n_seats": n_seats,
            "archetypes": archetypes,
        }, f, indent=2)

    print(f"\nChosen k={best_k} archetypes:")
    for a in archetypes:
        print(f"  Archetype {a['archetype']}: avg {a['avg_share_of_gb']}% of GB, "
              f"dominant in {a['n_seats_dominant']} seats — {a['label']}")

    print(f"\nWrote {OUTPUT / 'archetype_membership.csv'} and {OUTPUT / 'archetypes.json'}")


if __name__ == "__main__":
    main()
