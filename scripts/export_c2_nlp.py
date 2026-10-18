import json, sys
from pathlib import Path
import pyarrow.parquet as pq

def main():
    parquet = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/stage/c2/plan_network.parquet")
    df = pq.read_table(parquet).to_pandas()
    # histogram of nlp_score in 10 bins
    scores = df["nlp_score"].dropna().tolist()
    bins = [i/10 for i in range(11)]
    hist = [0]*10
    for s in scores:
        idx = min(int(s*10), 9)
        if idx < 0: idx = 0
        hist[idx] += 1
    # top 10 by nlp_score
    top = df.nlargest(10, "nlp_score")[["plan_name","network_type","confidence","nlp_score"]].to_dict(orient="records")
    out = {"histogram": [{"bin": f"{bins[i]:.1f}-{bins[i+1]:.1f}", "count": hist[i]} for i in range(10)],
           "top_plans": top,
           "total": len(df),
           "scored": len(scores)}
    print(json.dumps(out))

if __name__ == "__main__":
    main()
