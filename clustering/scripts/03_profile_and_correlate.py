"""
Turns the raw clustering output into something interpretable:

  - cluster_profiles_{nation}.json   per-cluster mean of every raw feature,
                                      an auto-generated short label from its
                                      most distinctive z-scored features, and
                                      its mean 2019/2024 vote shares + swing.
  - feature_vote_correlations.csv    Pearson correlation of every raw
                                      demographic variable against every
                                      party's 2024 share and swing, per
                                      nation - the direct "vote share/change
                                      correlates with x/y/z" answer,
                                      independent of what fed the clusters.
  - vote_regressions.csv             Ridge regression of each party's 2024
                                      share/swing on standardized
                                      demographics only (not other parties'
                                      shares - that would just recover the
                                      definitional fact that shares sum to
                                      ~100%), with cross-validated R² and
                                      standardized coefficients ("holding
                                      other demographics constant").

Usage:
    py 03_profile_and_correlate.py
"""
import json
import numpy as np
import pandas as pd
from pathlib import Path

from sklearn.linear_model import Ridge
from sklearn.model_selection import KFold, cross_val_predict
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import r2_score

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT = BASE_DIR / "output"
NATIONS = ["england", "scotland", "wales"]

DEMOGRAPHIC_ONLY_PREFIXES = ("y2019_", "y2024_", "swing_")


def demographic_cols(df):
    return [c for c in df.columns
            if c not in ("Seat", "County", "Region")
            and not c.startswith(DEMOGRAPHIC_ONLY_PREFIXES)]


def party_cols(df, kind):
    # kind in {"y2019", "y2024", "swing"}
    if kind in ("y2019", "y2024"):
        return [c for c in df.columns if c.startswith(f"{kind}_") and c.endswith("_share")]
    return [c for c in df.columns if c.startswith("swing_")]


def party_name(col):
    return col.replace("y2019_", "").replace("y2024_", "").replace("swing_", "").replace("_share", "")


def build_profiles(nation, feat, seg):
    df = feat.merge(seg[["Seat", "GMM_label"] + [c for c in seg.columns if c.startswith("Segment_")]],
                     on="Seat")
    demo_cols = demographic_cols(feat)
    y2019_cols = party_cols(feat, "y2019")
    y2024_cols = party_cols(feat, "y2024")
    swing_cols = party_cols(feat, "swing")
    all_numeric = demo_cols + y2019_cols + y2024_cols + swing_cols + ["y2019_Turnout", "y2024_Turnout"]
    all_numeric = list(dict.fromkeys(all_numeric))  # dedupe, keep order

    nation_mean = df[all_numeric].mean()
    nation_std = df[all_numeric].std(ddof=0).replace(0, np.nan)

    profiles = []
    for label, grp in df.groupby("GMM_label"):
        means = grp[all_numeric].mean()
        z = (means - nation_mean) / nation_std
        top_demo = z[demo_cols].abs().sort_values(ascending=False).head(5)
        descriptors = []
        for col in top_demo.index:
            direction = "high" if z[col] > 0 else "low"
            descriptors.append(f"{direction} {col} (z={z[col]:+.1f})")

        top_party_2024 = means[y2024_cols].sort_values(ascending=False).head(2)
        top_swing = z[swing_cols].sort_values(ascending=False).head(1)
        bottom_swing = z[swing_cols].sort_values(ascending=True).head(1)

        profiles.append({
            "segment": int(label),
            "n_seats": int(len(grp)),
            "seats": sorted(grp["Seat"].tolist()),
            "auto_label": "; ".join(descriptors),
            "leading_parties_2024": {party_name(k): round(v, 1) for k, v in top_party_2024.items()},
            "biggest_positive_swing": {party_name(k): round(float(v), 2) for k, v in top_swing.items()},
            "biggest_negative_swing": {party_name(k): round(float(v), 2) for k, v in bottom_swing.items()},
            "mean_features": {k: (round(float(v), 2) if pd.notna(v) else None) for k, v in means.items()},
        })

    profiles.sort(key=lambda p: -p["n_seats"])
    return profiles


def build_correlations(nation, feat):
    demo_cols = demographic_cols(feat)
    y2024_cols = party_cols(feat, "y2024")
    swing_cols = party_cols(feat, "swing")

    rows = []
    for target_col in y2024_cols + swing_cols:
        kind = "2024_share" if target_col in y2024_cols else "swing"
        party = party_name(target_col)
        for dcol in demo_cols:
            corr = feat[dcol].corr(feat[target_col])
            rows.append({
                "Nation": nation, "Party": party, "Target": kind,
                "Feature": dcol, "Pearson_r": round(corr, 3) if pd.notna(corr) else None,
            })
    return rows


def build_regressions(nation, feat):
    demo_cols = demographic_cols(feat)
    y2024_cols = party_cols(feat, "y2024")
    swing_cols = party_cols(feat, "swing")

    X = StandardScaler().fit_transform(feat[demo_cols].to_numpy(float))
    n = len(feat)
    n_splits = min(5, n)
    kf = KFold(n_splits=n_splits, shuffle=True, random_state=42)

    rows = []
    for target_col in y2024_cols + swing_cols:
        kind = "2024_share" if target_col in y2024_cols else "swing"
        party = party_name(target_col)
        y = feat[target_col].to_numpy(float)

        model = Ridge(alpha=10.0)
        y_pred = cross_val_predict(model, X, y, cv=kf)
        cv_r2 = r2_score(y, y_pred)

        model.fit(X, y)
        coefs = pd.Series(model.coef_, index=demo_cols).sort_values(key=np.abs, ascending=False)
        top = coefs.head(6)

        rows.append({
            "Nation": nation, "Party": party, "Target": kind,
            "CV_R2": round(cv_r2, 3),
            "Top_standardized_coefficients": {k: round(float(v), 2) for k, v in top.items()},
        })
    return rows


def main():
    all_correlations = []
    all_regressions = []

    for nation in NATIONS:
        feat = pd.read_csv(OUTPUT / f"features_{nation}.csv")
        seg = pd.read_csv(OUTPUT / f"segments_{nation}.csv")

        profiles = build_profiles(nation, feat, seg)
        with open(OUTPUT / f"cluster_profiles_{nation}.json", "w", encoding="utf-8") as f:
            json.dump(profiles, f, indent=2)

        all_correlations += build_correlations(nation, feat)
        all_regressions += build_regressions(nation, feat)

        print(f"{nation}: {len(profiles)} cluster profiles written")
        for p in profiles:
            print(f"  Segment {p['segment']} (n={p['n_seats']}): {p['auto_label']}")

    pd.DataFrame(all_correlations).to_csv(OUTPUT / "feature_vote_correlations.csv", index=False)

    reg_summary = pd.DataFrame([
        {"Nation": r["Nation"], "Party": r["Party"], "Target": r["Target"], "CV_R2": r["CV_R2"]}
        for r in all_regressions
    ])
    reg_summary.to_csv(OUTPUT / "vote_regressions_summary.csv", index=False)
    with open(OUTPUT / "vote_regressions.json", "w", encoding="utf-8") as f:
        json.dump(all_regressions, f, indent=2)

    print(f"\nWrote feature_vote_correlations.csv ({len(all_correlations)} rows)")
    print(f"Wrote vote_regressions.json / vote_regressions_summary.csv ({len(all_regressions)} rows)")


if __name__ == "__main__":
    main()
