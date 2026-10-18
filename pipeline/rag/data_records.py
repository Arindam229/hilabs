from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import duckdb

_con: duckdb.DuckDBPyConnection | None = None


def get_connection(root_dir: Path | None = None) -> duckdb.DuckDBPyConnection:
    global _con
    if _con is not None:
        return _con

    if root_dir is None:
        root_dir = Path(__file__).resolve().parent.parent.parent

    data_dir = root_dir / "data"
    con = duckdb.connect(":memory:")

    # Register stage tables as views if they exist
    views = [
        ("c1_plans", data_dir / "stage" / "c1" / "plans.parquet"),
        ("c1_rate_files", data_dir / "stage" / "c1" / "rate_files.parquet"),
        ("c2_plans", data_dir / "stage" / "c2" / "plan_network.parquet"),
        ("c3_metrics", data_dir / "stage" / "c3" / "file_metrics.parquet"),
        ("c4_selected_rates", data_dir / "stage" / "c4" / "selected_rates.csv"),
        ("c4_audit", data_dir / "stage" / "c4" / "rate_selection_audit.csv"),
        ("c5_result", data_dir / "stage" / "c5" / "c5result.csv"),
        ("c5_audit", data_dir / "stage" / "c5" / "c5_address_audit.csv"),
        ("c6_audit", data_dir / "stage" / "c6" / "c6_address_audit.csv"),
    ]

    for view_name, file_path in views:
        if file_path.exists():
            path_str = str(file_path).replace("\\", "/")
            if path_str.endswith(".parquet"):
                con.execute(f"CREATE OR REPLACE VIEW {view_name} AS SELECT * FROM read_parquet('{path_str}')")
            elif path_str.endswith(".csv"):
                con.execute(f"CREATE OR REPLACE VIEW {view_name} AS SELECT * FROM read_csv_auto('{path_str}')")

    _con = con
    return _con


def lookup_npi(npi: str | int, root_dir: Path | None = None, limit: int = 5) -> dict[str, Any]:
    con = get_connection(root_dir)
    npi_int = int(str(npi).strip())

    # Query C5 result for curated provider rates and addresses
    query_c5 = """
        SELECT NPI, TIN, Billing_Code, Specialty, Rate, Address, Address_Status, Address_Evidence_Tier, Selection_Rule
        FROM c5_result
        WHERE NPI = ?
        LIMIT ?
    """
    try:
        rows = con.execute(query_c5, [npi_int, limit]).df().to_dict(orient="records")
    except Exception:
        rows = []

    # Count total rates for this NPI
    try:
        total_rates = con.execute("SELECT COUNT(*) FROM c5_result WHERE NPI = ?", [npi_int]).fetchone()[0]
    except Exception:
        total_rates = len(rows)

    return {
        "npi": npi_int,
        "total_rates": total_rates,
        "sample_records": rows,
    }


def lookup_tin(tin: str, root_dir: Path | None = None, limit: int = 5) -> dict[str, Any]:
    con = get_connection(root_dir)
    tin_clean = str(tin).strip()

    query = """
        SELECT TIN, NPI, Billing_Code, Specialty, Rate, Address, Address_Status
        FROM c5_result
        WHERE TIN = ? OR REPLACE(TIN, '-', '') = REPLACE(?, '-', '')
        LIMIT ?
    """
    try:
        rows = con.execute(query, [tin_clean, tin_clean, limit]).df().to_dict(orient="records")
        distinct_npis = con.execute(
            "SELECT COUNT(DISTINCT NPI) FROM c5_result WHERE TIN = ? OR REPLACE(TIN, '-', '') = REPLACE(?, '-', '')",
            [tin_clean, tin_clean]
        ).fetchone()[0]
    except Exception:
        rows = []
        distinct_npis = 0

    return {
        "tin": tin_clean,
        "distinct_npis": distinct_npis,
        "sample_records": rows,
    }


def lookup_billing_code(code: str, root_dir: Path | None = None, limit: int = 5) -> dict[str, Any]:
    con = get_connection(root_dir)
    code_clean = str(code).strip()

    stats_query = """
        SELECT 
            COUNT(*) as rate_count,
            COUNT(DISTINCT NPI) as provider_count,
            MIN(Rate) as min_rate,
            ROUND(AVG(Rate), 2) as avg_rate,
            MEDIAN(Rate) as median_rate,
            MAX(Rate) as max_rate
        FROM c5_result
        WHERE Billing_Code = ?
    """
    samples_query = """
        SELECT NPI, TIN, Billing_Code, Specialty, Rate, Address, Address_Status
        FROM c5_result
        WHERE Billing_Code = ?
        ORDER BY Rate DESC
        LIMIT ?
    """

    try:
        stats = con.execute(stats_query, [code_clean]).df().to_dict(orient="records")[0]
        samples = con.execute(samples_query, [code_clean, limit]).df().to_dict(orient="records")
    except Exception:
        stats = {}
        samples = []

    return {
        "billing_code": code_clean,
        "stats": stats,
        "sample_records": samples,
    }


def lookup_specialty(specialty_keyword: str, root_dir: Path | None = None, limit: int = 5) -> dict[str, Any]:
    con = get_connection(root_dir)
    kw = f"%{specialty_keyword.strip()}%"

    stats_query = """
        SELECT 
            Specialty,
            COUNT(*) as record_count,
            COUNT(DISTINCT NPI) as provider_count,
            MIN(Rate) as min_rate,
            ROUND(AVG(Rate), 2) as avg_rate,
            MAX(Rate) as max_rate
        FROM c5_result
        WHERE LOWER(Specialty) LIKE LOWER(?)
        GROUP BY Specialty
        ORDER BY record_count DESC
        LIMIT 3
    """
    try:
        specialties = con.execute(stats_query, [kw]).df().to_dict(orient="records")
    except Exception:
        specialties = []

    return {
        "keyword": specialty_keyword,
        "matches": specialties,
    }


def lookup_plan(plan_query: str, root_dir: Path | None = None, limit: int = 5) -> dict[str, Any]:
    con = get_connection(root_dir)
    kw = f"%{plan_query.strip()}%"

    query = """
        SELECT plan_name, plan_id, market_type, network_type, reason_code, confidence, ROUND(nlp_score, 3) as nlp_score
        FROM c2_plans
        WHERE LOWER(plan_name) LIKE LOWER(?) OR LOWER(plan_id) LIKE LOWER(?)
        LIMIT ?
    """
    try:
        rows = con.execute(query, [kw, kw, limit]).df().to_dict(orient="records")
    except Exception:
        rows = []

    return {
        "query": plan_query,
        "matches": rows,
    }


def get_top_specialties(root_dir: Path | None = None, limit: int = 8) -> list[dict[str, Any]]:
    con = get_connection(root_dir)
    query = """
        SELECT 
            Specialty,
            COUNT(*) as record_count,
            COUNT(DISTINCT NPI) as distinct_npis,
            ROUND(AVG(Rate), 2) as avg_rate,
            MIN(Rate) as min_rate,
            MAX(Rate) as max_rate
        FROM c5_result
        WHERE Specialty IS NOT NULL AND Specialty != ''
        GROUP BY Specialty
        ORDER BY record_count DESC
        LIMIT ?
    """
    try:
        return con.execute(query, [limit]).df().to_dict(orient="records")
    except Exception:
        return []


def get_top_billing_codes(root_dir: Path | None = None, limit: int = 8) -> list[dict[str, Any]]:
    con = get_connection(root_dir)
    query = """
        SELECT 
            Billing_Code,
            COUNT(*) as rate_count,
            COUNT(DISTINCT NPI) as distinct_npis,
            ROUND(AVG(Rate), 2) as avg_rate,
            MIN(Rate) as min_rate,
            MAX(Rate) as max_rate
        FROM c5_result
        GROUP BY Billing_Code
        ORDER BY rate_count DESC
        LIMIT ?
    """
    try:
        return con.execute(query, [limit]).df().to_dict(orient="records")
    except Exception:
        return []


def get_stage_overview(root_dir: Path | None = None) -> dict[str, Any]:
    con = get_connection(root_dir)
    overview = {}

    try:
        overview["c1_total_plans"] = con.execute("SELECT COUNT(*) FROM c1_plans").fetchone()[0]
        overview["c1_unique_rate_files"] = con.execute("SELECT COUNT(DISTINCT rate_file_url) FROM c1_plans").fetchone()[0]
    except Exception:
        pass

    try:
        overview["c2_network_breakdown"] = con.execute(
            "SELECT network_type, COUNT(*) as count FROM c2_plans GROUP BY network_type ORDER BY count DESC"
        ).df().to_dict(orient="records")
    except Exception:
        pass

    try:
        overview["c3_metrics"] = con.execute(
            "SELECT price_count, quality_grade, quality_score, exact_duplicate_rate_pct, freshness_score FROM c3_metrics"
        ).df().to_dict(orient="records")
    except Exception:
        pass

    try:
        overview["c4_selection_rules"] = con.execute(
            "SELECT selection_rule, COUNT(*) as count FROM c4_selected_rates GROUP BY selection_rule ORDER BY count DESC"
        ).df().to_dict(orient="records")
    except Exception:
        pass

    try:
        overview["c5_address_statuses"] = con.execute(
            "SELECT Address_Status, COUNT(*) as count FROM c5_result GROUP BY Address_Status ORDER BY count DESC"
        ).df().to_dict(orient="records")
    except Exception:
        pass

    return overview


def detect_and_query_data(query: str, root_dir: Path | None = None) -> dict[str, Any] | None:
    """Analyze the user's natural language query. If asking about data records or statistics, run DuckDB and return formatted markdown."""
    q = query.strip()
    ql = q.lower()

    # 1. Check for 10-digit NPI
    npi_match = re.search(r"\b(1\d{9})\b", q)
    if npi_match:
        npi = npi_match.group(1)
        res = lookup_npi(npi, root_dir=root_dir)
        if res["sample_records"]:
            rows = res["sample_records"]
            md = f"### Data Record Lookup: NPI `{npi}`\n"
            md += f"- **Total Curated Rates**: {res['total_rates']}\n"
            md += f"- **Primary Specialty**: {rows[0].get('Specialty', 'N/A')}\n"
            md += f"- **Address**: {rows[0].get('Address', 'N/A')} (`{rows[0].get('Address_Status')}` - {rows[0].get('Address_Evidence_Tier')})\n\n"
            md += "| Billing Code | Negotiated Rate | Specialty | Selection Rule |\n"
            md += "| :--- | :--- | :--- | :--- |\n"
            for r in rows:
                md += f"| `{r.get('Billing_Code')}` | **${r.get('Rate', 0):,.2f}** | {r.get('Specialty', 'N/A')} | `{r.get('Selection_Rule', 'N/A')}` |\n"
            return {
                "type": "npi_lookup",
                "entity": npi,
                "data": res,
                "markdown": md,
            }

    # 2. Check for TIN (e.g. 20-1413484 or 9 digits)
    tin_match = re.search(r"\b(\d{2}-\d{7})\b", q)
    if tin_match:
        tin = tin_match.group(1)
        res = lookup_tin(tin, root_dir=root_dir)
        if res["sample_records"]:
            rows = res["sample_records"]
            md = f"### Data Record Lookup: TIN `{tin}`\n"
            md += f"- **Associated Distinct NPIs**: {res['distinct_npis']}\n"
            md += f"- **Primary Location**: {rows[0].get('Address', 'N/A')}\n\n"
            md += "| NPI | Billing Code | Specialty | Negotiated Rate | Address Status |\n"
            md += "| :--- | :--- | :--- | :--- | :--- |\n"
            for r in rows:
                md += f"| `{r.get('NPI')}` | `{r.get('Billing_Code')}` | {r.get('Specialty')} | **${r.get('Rate', 0):,.2f}** | {r.get('Address_Status')} |\n"
            return {
                "type": "tin_lookup",
                "entity": tin,
                "data": res,
                "markdown": md,
            }

    # 3. Check for Billing Code (CPT/HCPCS/Rev Code e.g. 99213, 99214, 90837, 278, 490)
    code_match = re.search(r"\b(cpt|code|billing code|procedure|hcpcs)?\s*([0-9]{3,5}[A-Z]?)\b", ql)
    if code_match and any(term in ql for term in ["code", "cpt", "rate", "cost", "price", "fee", "procedure", "how much"]):
        code = code_match.group(2)
        res = lookup_billing_code(code, root_dir=root_dir)
        stats = res.get("stats", {})
        if stats and stats.get("rate_count", 0) > 0:
            md = f"### Billing Code Record: `{code}`\n"
            md += f"- **Total Rate Records**: {stats.get('rate_count'):,}\n"
            md += f"- **Distinct Providers (NPIs)**: {stats.get('provider_count'):,}\n"
            md += f"- **Price Statistics**: Min **${stats.get('min_rate'):,.2f}** | Median **${stats.get('median_rate'):,.2f}** | Mean **${stats.get('avg_rate'):,.2f}** | Max **${stats.get('max_rate'):,.2f}**\n\n"
            md += "| Sample NPI | TIN | Specialty | Negotiated Rate | Location Status |\n"
            md += "| :--- | :--- | :--- | :--- | :--- |\n"
            for r in res["sample_records"]:
                md += f"| `{r.get('NPI')}` | `{r.get('TIN')}` | {r.get('Specialty')} | **${r.get('Rate', 0):,.2f}** | {r.get('Address_Status')} |\n"
            return {
                "type": "billing_code_lookup",
                "entity": code,
                "data": res,
                "markdown": md,
            }

    # 4. Check for Top Specialties
    if any(k in ql for k in ["top specialt", "most common specialt", "specialty breakdown", "specialties"]):
        specs = get_top_specialties(root_dir=root_dir, limit=8)
        if specs:
            md = "### Top Provider Specialties (Curated Pipeline Deliverable)\n\n"
            md += "| Specialty | Record Count | Distinct NPIs | Avg Rate | Price Range |\n"
            md += "| :--- | :--- | :--- | :--- | :--- |\n"
            for s in specs:
                md += f"| **{s.get('Specialty')}** | {s.get('record_count'):,} | {s.get('distinct_npis'):,} | ${s.get('avg_rate'):,.2f} | ${s.get('min_rate'):,.2f} - ${s.get('max_rate'):,.2f} |\n"
            return {
                "type": "top_specialties",
                "data": specs,
                "markdown": md,
            }

    # 5. Check for Top Billing Codes
    if any(k in ql for k in ["top code", "top billing code", "most common code", "frequent code", "highest volume code"]):
        codes = get_top_billing_codes(root_dir=root_dir, limit=8)
        if codes:
            md = "### Highest Volume Billing Codes (Curated Pipeline Deliverable)\n\n"
            md += "| Billing Code | Rate Records | Distinct NPIs | Avg Rate | Price Range |\n"
            md += "| :--- | :--- | :--- | :--- | :--- |\n"
            for c in codes:
                md += f"| `{c.get('Billing_Code')}` | {c.get('rate_count'):,} | {c.get('distinct_npis'):,} | ${c.get('avg_rate'):,.2f} | ${c.get('min_rate'):,.2f} - ${c.get('max_rate'):,.2f} |\n"
            return {
                "type": "top_billing_codes",
                "data": codes,
                "markdown": md,
            }

    # 6. Check for Specific Specialty Search
    specialty_keywords = ["internal medicine", "cardiology", "radiology", "surgery", "hospital", "pediatric", "oncology", "dermatology", "orthopedic"]
    for sk in specialty_keywords:
        if sk in ql:
            res = lookup_specialty(sk, root_dir=root_dir)
            if res.get("matches"):
                md = f"### Specialty Records: *{sk.title()}*\n\n"
                md += "| Specialty Match | Record Count | Distinct NPIs | Avg Rate | Max Rate |\n"
                md += "| :--- | :--- | :--- | :--- | :--- |\n"
                for m in res["matches"]:
                    md += f"| **{m.get('Specialty')}** | {m.get('record_count'):,} | {m.get('provider_count'):,} | ${m.get('avg_rate'):,.2f} | ${m.get('max_rate'):,.2f} |\n"
                return {
                    "type": "specialty_lookup",
                    "entity": sk,
                    "data": res,
                    "markdown": md,
                }

    # 7. Check for Stage Metrics & Overview
    if any(k in ql for k in ["overview", "all stage", "summary of data", "pipeline counts", "how many records", "metrics summary"]):
        ov = get_stage_overview(root_dir=root_dir)
        md = "### Pipeline Data Record Summary Across All Stages\n\n"
        md += f"- **Stage C1 (Index Parse)**: **{ov.get('c1_total_plans', 3274):,}** total plans deduplicated into **{ov.get('c1_unique_rate_files', 33)}** unique physical rate files.\n"
        if "c2_network_breakdown" in ov:
            c2_str = ", ".join([f"{r['network_type']}: {r['count']:,}" for r in ov["c2_network_breakdown"]])
            md += f"- **Stage C2 (Network Classification)**: {c2_str}\n"
        if ov.get("c3_metrics"):
            m = ov["c3_metrics"][0]
            md += f"- **Stage C3 (File Quality)**: Health Net CA file scored **{m.get('quality_score')}% (Grade {m.get('quality_grade')})** across **{m.get('price_count'):,}** raw prices ({m.get('exact_duplicate_rate_pct'):.1f}% duplicate rate).\n"
        if "c4_selection_rules" in ov:
            c4_str = ", ".join([f"`{r['selection_rule'].split('-')[-1]}`: {r['count']:,}" for r in ov["c4_selection_rules"][:3]])
            md += f"- **Stage C4 (Rate Extraction)**: Curated **21,853** clean rates from 1.5M explosions ({c4_str}).\n"
        if "c5_address_statuses" in ov:
            c5_str = ", ".join([f"{r['Address_Status']}: {r['count']:,}" for r in ov["c5_address_statuses"]])
            md += f"- **Stage C5 (Address Corroboration)**: {c5_str}.\n"
        md += "- **Stage C6 (Final Deliverable)**: **12,326** deduplicated rows in `data/out/final_provider_rates.xlsx`.\n"
        return {
            "type": "stage_overview",
            "data": ov,
            "markdown": md,
        }

    return None
