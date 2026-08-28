import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
RAW = BASE_DIR / "data" / "raw"
INTERMEDIATE = BASE_DIR / "data" / "intermediate"

# ---------------------------------------------------
# Files
# ---------------------------------------------------

projection = pd.read_csv(INTERMEDIATE / "projected_results.csv")

tactical = RAW / "Tactical.xlsx"

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

# ---------------------------------------------------
# Winners sheet
# ---------------------------------------------------

winners = pd.read_excel(
    tactical,
    sheet_name="Winners",
    header=None,
    names=["Seat", "Winner"]
)

winner_lookup = dict(zip(
    winners.Seat,
    winners.Winner
))

# ---------------------------------------------------
# Tactical % + willingness matrix
# ---------------------------------------------------
# TVPCT is a matrix: column "TVPct" is each donor's flat "% of its own
# voters willing to consider tactical voting at all" (unchanged role from
# before); every other column is that donor's per-recipient willingness %
# - how appealing each specific recipient is to its tactical-considering
# voters. These don't sum to 100 across a row - they're independent
# appeal scores, not a split.

PARTY_ALIASES = {"Lib Dem": "LibDem"}


def normalize(name):
    return PARTY_ALIASES.get(name, name)


tv = pd.read_excel(tactical, sheet_name="TVPCT", header=0, index_col=0)
tv.index = [normalize(i) for i in tv.index]

tv_pct = (tv["TVPct"] / 100).to_dict()

# Ensure every party has an entry
for p in parties:
    tv_pct.setdefault(p, 0)

tv_willingness = (
    tv.drop(columns="TVPct")
      .rename(columns=normalize)
      .reindex(index=parties, columns=parties)
      .fillna(0)
    / 100
)

# ---------------------------------------------------
# Tactical preference matrix
# ---------------------------------------------------

matrix = pd.read_excel(
    tactical,
    sheet_name="TVMatrix",
    index_col=0
)

# Keep only current parties
matrix = matrix.loc[parties, parties]

df = projection

results = []

# Tier 1 (within 5pts of the leader, or the incumbent) = full-strength
# tactical destination, and never tactically votes itself - it's already
# winning. Tier 2 (5-10pts behind) = half-strength destination, and can
# itself tactically vote for tier 1 using 40% of its normal TVPCT rate.
# Tier 3 (10-15pts behind) = quarter-strength destination, and can itself
# tactically vote for tier 1 or tier 2 using 80% of its normal TVPCT rate.
# Anything more than 15pts behind the leader isn't tiered at all, and
# tactically votes for any tiered party at its full normal TVPCT rate.
TIER_STRENGTH = {1: 1.0, 2: 0.5, 3: 0.25}
DONOR_TVPCT_MULT = {2: 0.4, 3: 0.8}  # non-winnable donors use 1.0 (full)


def cascading_transfer(donor, votes, tier):
    """Walks the donor's TVMatrix preference ranking (most preferred
    first), restricted to tiered parties in a STRICTLY BETTER tier than
    the donor's own (or, for a non-tiered donor, any tiered party at
    all). At each ranked candidate, the amount of whatever's still left
    that actually moves there is scaled by BOTH that candidate's personal
    appeal to this donor's tactical voters (the TVPCT willingness matrix)
    AND that candidate's own tier strength (is voting for them practically
    worth it, given their own viability) - the rest cascades to the
    next-ranked candidate. Whatever's left once the ranked list of
    eligible candidates runs out simply stays with the donor - it never
    overflows anywhere else."""

    donor_tier = tier.get(donor)

    if donor_tier == 1:
        return

    mult = DONOR_TVPCT_MULT.get(donor_tier, 1.0)

    transfer = votes[donor] * tv_pct[donor] * mult

    if transfer <= 0:
        return

    prefs = matrix.loc[donor]

    # Ignore -1 entries; most preferred (lowest rank number) first.
    ranked = (
        prefs[prefs > 0]
        .sort_values()
        .index
    )

    def eligible(party):
        if party not in tier:
            return False
        if donor_tier is None:
            return True
        return tier[party] < donor_tier

    ranked_eligible = [p for p in ranked if eligible(p)]

    remaining = transfer

    for candidate in ranked_eligible:
        if remaining <= 0:
            break
        willingness = tv_willingness.loc[donor, candidate]
        amount = remaining * willingness * TIER_STRENGTH[tier[candidate]]
        votes[candidate] += amount
        remaining -= amount

    votes[donor] -= (transfer - remaining)


# ---------------------------------------------------
# Every constituency
# ---------------------------------------------------

for _, row in df.iterrows():

    seat = row["Seat"]

    # Current projected vote

    votes = {
        p: row.get(p, 0)
        for p in parties
    }

    # -------------------------
    # Tier every party by how far behind the projected leader it is;
    # the incumbent is always tier 1 regardless of its own gap.
    # -------------------------

    leader = max(votes, key=votes.get)
    leader_share = votes[leader]

    tier = {}
    for party in parties:
        gap = leader_share - votes[party]
        if gap <= 5:
            tier[party] = 1
        elif gap <= 10:
            tier[party] = 2
        elif gap <= 15:
            tier[party] = 3
        # else: not a tactical-voting destination at all

    previous = winner_lookup.get(seat)
    if previous in parties:
        tier[previous] = 1

    # -------------------------
    # No tactical voting
    # -------------------------

    if len(tier) <= 1:

        out = {"Seat": seat}
        out.update(votes)
        results.append(out)
        continue

    # -------------------------------------------------
    # Every party except tier 1 (the winning tier) tactically votes via
    # TVPCT/TVMatrix, cascading through strictly-better tiers at each
    # tier's strength.
    # -------------------------------------------------

    for donor in parties:
        if tier.get(donor) == 1:
            continue
        cascading_transfer(donor, votes, tier)

    out = {"Seat": seat}
    out.update(votes)

    results.append(out)

# ---------------------------------------------------
# Save
# ---------------------------------------------------

output = (
    pd.DataFrame(results)
      .sort_values("Seat")
      .reset_index(drop=True)
)

output.to_csv(INTERMEDIATE / "projected_results_tactical.csv", index=False)

print(output.head())
