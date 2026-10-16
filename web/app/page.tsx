"use client";

import { ChangeEvent, useState } from "react";

type RecordResult = {
  source_id: string;
  normalized: Record<string, string>;
  action: string;
  reason_codes: string[];
  review_required: boolean;
};

type RunResult = {
  run_id: string;
  summary: { input_count: number; output_count: number; review_count: number };
  records: RecordResult[];
};

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [run, setRun] = useState<RunResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    setFile(event.target.files?.[0] ?? null);
    setRun(null);
    setError(null);
  }

  async function processFile() {
    if (!file) return;
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append("file", file);
    try {
      const response = await fetch(`${API}/process`, { method: "POST", body: form });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? "Processing failed");
      setRun(payload);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Processing failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <header>
        <p className="eyebrow">LOCAL-FIRST DATA QUALITY</p>
        <h1>HiLabs workflow skeleton</h1>
        <p>Upload CSV. Validate, normalize, preserve audit trail, export exceptions.</p>
      </header>

      <section className="upload-card">
        <label htmlFor="file">Provider or operational CSV</label>
        <input id="file" type="file" accept=".csv,text/csv" onChange={chooseFile} />
        <button onClick={processFile} disabled={!file || busy}>
          {busy ? "Processing…" : "Process file"}
        </button>
        {file && <small>{file.name}</small>}
        {error && <p className="error">{error}</p>}
      </section>

      {run && (
        <>
          <section className="metrics" aria-label="Run summary">
            <Metric label="Input" value={run.summary.input_count} />
            <Metric label="Output" value={run.summary.output_count} />
            <Metric label="Review queue" value={run.summary.review_count} />
            <a className="export" href={`${API}/runs/${run.run_id}/export`}>Download audit CSV</a>
          </section>
          <section className="results">
            <h2>Evidence queue</h2>
            <p>Run {run.run_id}. PS-specific validation stages plug in after this audited core.</p>
            <div className="table-wrap"><table>
              <thead><tr><th>Source ID</th><th>Action</th><th>Reasons</th><th>Review</th></tr></thead>
              <tbody>{run.records.map((record) => (
                <tr key={record.source_id}>
                  <td>{record.source_id}</td><td>{record.action}</td>
                  <td>{record.reason_codes.join(", ") || "—"}</td>
                  <td>{record.review_required ? "Yes" : "No"}</td>
                </tr>
              ))}</tbody>
            </table></div>
          </section>
        </>
      )}
    </main>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong></div>;
}
