
import json
import math
import sys
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq


def main():
    parquet = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path("data/stage/c2/plan_network.parquet")
    )

    if not parquet.is_file():
        raise FileNotFoundError(f"Parquet file not found: {parquet.resolve()}")

    df = pq.read_table(parquet).to_pandas()

    required = {
        "nlp_score",
        "plan_name",
        "network_type",
        "confidence",
    }
    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            f"Missing Parquet columns: {sorted(missing)}. "
            f"Available columns: {list(df.columns)}"
        )

    # Convert scores safely to numeric values.
    df["nlp_score"] = pd.to_numeric(
        df["nlp_score"], errors="coerce"
    )

    # Ignore null, NaN and infinite scores.
    valid_mask = df["nlp_score"].map(
        lambda x: pd.notna(x) and math.isfinite(float(x))
    )
    scored_df = df.loc[valid_mask].copy()

    # Ten histogram bins covering scores from 0 to 1.
    bins = [i / 10 for i in range(11)]
    hist = [0] * 10

    for score in scored_df["nlp_score"]:
        idx = max(0, min(int(float(score) * 10), 9))
        hist[idx] += 1

    # Highest NLP scores first.
    top_df = scored_df.nlargest(
        10, "nlp_score"
    )[["plan_name", "network_type", "confidence", "nlp_score"]]

    # pandas converts missing values into JSON null.
    top_plans = json.loads(top_df.to_json(orient="records"))

    result = {
        "histogram": [
            {
                "bin": f"{bins[i]:.1f}-{bins[i + 1]:.1f}",
                "count": hist[i],
            }
            for i in range(10)
        ],
        "top_plans": top_plans,
        "total": len(df),
        "scored": len(scored_df),
    }

    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
