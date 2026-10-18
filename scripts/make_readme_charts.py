# Regenerate README charts from pipeline outputs: uv run --with matplotlib python scripts/make_readme_charts.py .
import collections
import io
import json
import sys
import zipfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pyarrow.parquet as pq
from matplotlib.patches import FancyBboxPatch

ROOT = Path(sys.argv[1]); OUT = ROOT / "docs/assets"; OUT.mkdir(parents=True, exist_ok=True)
D = ROOT / "data"
INK, MUTED, ACC, ACC2, WARN = "#1f2937", "#6b7280", "#2563eb", "#93c5fd", "#d97706"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False,
                     "axes.spines.right": False, "axes.edgecolor": "#d1d5db", "axes.labelcolor": INK,
                     "xtick.color": INK, "ytick.color": INK})


def save(fig, name, source):
    fig.text(0.01, 0.01, f"Source: {source}", fontsize=7.5, color=MUTED)
    fig.savefig(OUT / name, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", name)


def barh(ax, labels, values, colors=None, fmt="{:,}"):
    y = range(len(labels))
    ax.barh(list(y), values, color=colors or ACC)
    ax.set_yticks(list(y), labels)
    ax.invert_yaxis()
    for i, v in enumerate(values):
        ax.text(v, i, " " + fmt.format(v), va="center", fontsize=9, color=INK)
    ax.set_xlim(0, max(values) * 1.18)


# 1. Pipeline architecture diagram
fig, ax = plt.subplots(figsize=(12, 4.2)); ax.axis("off"); ax.set_xlim(0, 12); ax.set_ylim(0, 4.2)
stages = [("C1", "Parse index\nfiles"), ("C2", "PPO\nnetwork"), ("C3", "Grade\nfiles"), ("C4", "Extract\nrates"),
          ("C5", "Address\nengine"), ("C6", "Final rate\nfile"), ("C7", "Cost-\neffectiveness")]
for i, (c, t) in enumerate(stages):
    x = 0.3 + i * 1.68
    ax.add_patch(FancyBboxPatch((x, 2.1), 1.3, 1.1, boxstyle="round,pad=0.04,rounding_size=0.12",
                                fc=ACC if c in ("C3", "C5") else "#eff6ff", ec=ACC, lw=1.4))
    col = "white" if c in ("C3", "C5") else INK
    ax.text(x + 0.65, 2.92, c, ha="center", fontsize=12, weight="bold", color=col)
    ax.text(x + 0.65, 2.45, t, ha="center", va="center", fontsize=8.5, color=col)
    if i < len(stages) - 1:
        ax.annotate("", (x + 1.66, 2.65), (x + 1.32, 2.65), arrowprops={"arrowstyle": "->", "color": MUTED, "lw": 1.3})
srcs = ["NPPES", "CMS DAC", "Reassignment", "Health Net\nPPO directory", "Medicare\nclaims 2024", "PECOS", "CMS NPD"]
for j, s in enumerate(srcs):
    x = 3.25 + j * 1.18
    ax.add_patch(FancyBboxPatch((x, 0.35), 1.05, 0.75, boxstyle="round,pad=0.03,rounding_size=0.1", fc="#fff7ed", ec=WARN, lw=1))
    ax.text(x + 0.52, 0.72, s, ha="center", va="center", fontsize=7.6, color=INK)
    ax.annotate("", (7.3, 2.08), (x + 0.52, 1.12), arrowprops={"arrowstyle": "->", "color": WARN, "lw": 0.8, "alpha": 0.7})
ax.text(0.3, 3.85, "One archive in → streamed stage by stage → manifest + rule IDs at every step", fontsize=10.5, color=INK, weight="bold")
ax.text(0.3, 0.75, "Address evidence\nsources (C5):", fontsize=8.5, color=WARN, weight="bold")
save(fig, "pipeline_architecture.png", "pipeline/__main__.py, Makefile")

# 2. C2 plan classification
plans = pq.read_table(D / "stage/c2/plan_network.parquet").to_pandas()
rc = plans["reason_code"].value_counts()
labels = {"R-C2-01-NON_GROUP_MARKET": "Out of scope: non-group market", "R-C2-02-NON_CA_SCOPE": "Out of scope: not California",
          "R-C2-03-RESTRICTIVE_TOKEN": "HMO / EPO / POS token", "R-C2-04-PPO_TOKEN": "PPO token → PPO",
          "R-C2-05-EOA_UNVERIFIED": "EOA: unresolved", "R-C2-06-INSUFFICIENT_PLAN_EVIDENCE": "No network evidence: unresolved"}
keys = [k for k in labels if k in rc.index]
fig, ax = plt.subplots(figsize=(9, 3.6))
barh(ax, [f"{labels[k]}\n({k[:7]})" for k in keys], [int(rc[k]) for k in keys],
     [ACC if "PPO_TOKEN" in k else "#cbd5e1" if k.startswith(("R-C2-01", "R-C2-02")) else ACC2 for k in keys])
ax.set_title(f"C2 · {len(plans):,} plans classified → {int(rc.get('R-C2-04-PPO_TOKEN', 0)):,} CA commercial-group PPO plans",
             loc="left", fontsize=11, weight="bold", color=INK)
ax.set_xlabel("Plans")
save(fig, "c2_classification.png", "data/stage/c2/plan_network.parquet")

# 3. C3 quality metrics
m = pq.read_table(D / "stage/c3/file_metrics.parquet").to_pylist()[0]
metrics = [("Uniqueness (no duplicates)", 100 - m["exact_duplicate_rate_pct"], 2),
           ("Cohort outlier sanity", 100 - (m["cohort_outlier_rate_pct_estimate"] or 0), 2),
           ("Code coverage (HiLabs-weighted)", m["code_coverage_weighted_pct"], 3),
           ("Medicare plausibility", 100 - (m["medicare_out_of_band_pct"] or 0), 2),
           ("NPI check-digit validity", m["npi_validity_pct"], 2),
           ("Required fields complete", m["required_field_completeness_pct"], 1),
           ("Pointer integrity", m["pointer_integrity_pct"], 1),
           ("Freshness", m["freshness_score"], 1),
           ("Rate validity ($0 / negative)", 100 - m["zero_or_negative_rate_pct"] - m["invalid_rate_pct"], 1)]
fig, ax = plt.subplots(figsize=(9, 4.2))
barh(ax, [f"{n}  ×{w}" for n, _, w in metrics], [round(v, 1) for _, v, _ in metrics],
     [WARN if v < 90 else ACC for _, v, _ in metrics], fmt="{:.1f}")
ax.set_xlim(0, 115)
ax.set_title(f"C3 · Health Net CA file: {m['quality_score']} / 100 (grade {m['quality_grade']}) over {m['price_count']:,} prices",
             loc="left", fontsize=11, weight="bold", color=INK)
ax.set_xlabel("Metric score (0–100), ×weight in the blend")
save(fig, "c3_quality_metrics.png", "data/stage/c3/file_metrics.parquet")

# 4. C4 extraction funnel (log scale)
s = json.loads((D / "stage/c4/c4_summary.json").read_text())
steps = [("Services (in_network items)", s["service_entries_processed"]),
         ("Negotiated-rate entries", s["negotiated_rate_entries_processed"]),
         ("NPI × price records", s["output_records_generated"]),
         ("Exact duplicates removed", s["exact_duplicates_removed"]),
         ("Curated NPI × TIN × code rates", s["curated_records"])]
fig, ax = plt.subplots(figsize=(9, 3.2))
barh(ax, [n for n, _ in steps], [v for _, v in steps], [ACC2, ACC2, ACC, "#cbd5e1", ACC])
ax.set_xscale("log"); ax.set_xlim(1000, 1.2e7)
ax.set_title(f"C4 · {s['distinct_npis_curated']:,} NPIs · {s['distinct_tins_curated']:,} TINs · 0 unresolved provider references",
             loc="left", fontsize=11, weight="bold", color=INK)
save(fig, "c4_extraction_funnel.png", "data/stage/c4/c4_summary.json (log scale)")

# 5. C5 heuristic scoring weights (from pipeline/stages/c5_address.py score_address_candidate)
w = [("CMS National Provider Directory", 60), ("CMS Doctors & Clinicians (DAC)", 50), ("Health Net PPO directory: shown", 50),
     ("Medicare claims address (2024)", 40), ("NPPES secondary practice location", 30),
     ("CMS reassignment (+ name match)", 25), ("≥ 2 independent source families", 20),
     ("Health Net PPO directory: hidden", 20), ("NPPES primary address (~80% stale)", 10)]
fig, ax = plt.subplots(figsize=(9, 4))
barh(ax, [n for n, _ in w], [v for _, v in w], [ACC if v >= 50 else ACC2 if v >= 25 else "#cbd5e1" for _, v in w], fmt="+{}")
ax.axvline(60, color=WARN, ls="--", lw=1.2); ax.text(60.5, 8.6, "VERIFIED ≥ 60", color=WARN, fontsize=8.5)
ax.axvline(30, color=MUTED, ls=":", lw=1); ax.text(30.5, 8.6, "PROBABLE ≥ 30", color=MUTED, fontsize=8.5)
ax.set_title("C5 · Heuristic address scoring: points per evidence source (P.O. box −60)", loc="left", fontsize=11, weight="bold", color=INK)
ax.set_xlabel("Points")
save(fig, "c5_scoring_weights.png", "pipeline/stages/c5_address.py · score_address_candidate()")

# 6. C6 verification by source (offline analysis of the C6 file, 2026-10-18; counts in README §7)
v = [("NPPES only (unverified)", 4892, "#cbd5e1"), ("Health Net PPO: hidden listing", 3650, ACC2),
     ("Health Net PPO directory: shown", 1675, ACC), ("Medicare claims 2024", 1030, ACC),
     ("CMS DAC", 88, ACC), ("CMS National Provider Directory", 61, ACC)]
fig, ax = plt.subplots(figsize=(9, 3.4))
barh(ax, [n for n, _, _ in v], [x for _, x, _ in v], [c for _, _, c in v])
ax.set_title("C6 · 11,396 final rows: verified by a second source — 4.8% → 25.0% strong / 57.1% total",
             loc="left", fontsize=11, weight="bold", color=INK)
ax.set_xlabel("Rows (each credited once to its strongest source)")
save(fig, "c6_verification_by_source.png", "offline analysis of data/out/final_provider_rates.xlsx, 2026-10-18")

# 7. C7 quadrants (in-memory run on the current C6 file)
sys.path.insert(0, str(ROOT))
from metrics import load_benchmark, load_pfs_table
from pipeline.config import load_config
from pipeline.stages import c7

cfg = load_config(); A = cfg.archive
z2c = c7.load_zip_to_county(A); c2l, _ = c7.load_county_to_locality(A, set(z2c.values())); g = c7.load_ca_gpci_by_locality(A)
with zipfile.ZipFile(A) as o:
    pfs = load_pfs_table(io.BytesIO(o.read(c7._dataset_member(A, "cms_pfs/rvu26d-updated-08-26-2026.zip"))))
    bm = load_benchmark(io.BytesIO(o.read(c7._dataset_member(A, "Rate Benchmarking Individual Weights_Hackathon.xlsx"))))
rows = c7._read_c6_rows(D / "out/final_provider_rates.xlsx")
c7.attach_medicare_ratios(rows, pfs, z2c, c2l, g); c7.compute_reference_ratios(rows)
prov, _ = c7.aggregate_providers(rows, bm["proc_weights"])
q = collections.Counter(p["quadrant"] for p in prov)
order = ["Broad Network Value", "Preferred Niche", "High-Cost Broad Scope", "Niche Watchlist", "Insufficient data"]
fig, ax = plt.subplots(figsize=(9, 3))
barh(ax, order, [q[k] for k in order], [ACC, ACC2, WARN, "#fdba74", "#cbd5e1"])
ax.set_title(f"C7 · {len(prov):,} providers: Medicare-anchored, locality-adjusted price vs peers × breadth",
             loc="left", fontsize=11, weight="bold", color=INK)
ax.set_xlabel("Providers")
save(fig, "c7_quadrants.png", "pipeline/stages/c7.py on data/out/final_provider_rates.xlsx")
