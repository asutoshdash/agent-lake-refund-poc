import React, {useState, useEffect} from "react";
import {createRoot} from "react-dom/client";

const scenarios = {
  pending: "Pending refund", settled: "Settled refund", failed: "Failed refund",
  timeout: "Processor timeout", missing: "Missing evidence", followup: "Pending → settled (two turns)"
};

function Console() {
  const [scenario, setScenario] = useState("pending");
  const [question, setQuestion] = useState("Has my refund gone through?");
  const [rows, setRows] = useState([]);
  const [evaluate, setEvaluate] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const [history, setHistory] = useState({runs: []});
  const [saved, setSaved] = useState(null);

  async function refreshHistory() {
    try {
      const response = await fetch("/api/runs");
      setHistory(await response.json());
    } catch {
      setHistory({error: "Could not load saved runs."});
    }
  }
  useEffect(() => { refreshHistory(); }, []);

  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    setRows([]);
    setSaved(null);
    try {
      const response = await fetch("/api/query", {method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({case: scenario, question, evaluate})});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Request failed. Try again.");
      setRows(data.turns);
      setSaved(data);
    } catch (e) {
      setError(e instanceof TypeError ? "Could not reach the local server. Check the connection and retry." : e.message);
    } finally {
      setBusy(false);
      refreshHistory();
    }
  }
  return <><header><div className="brand"><span aria-hidden="true">≋</span> Agent Lake</div></header>
    <main><h1>Refund console</h1><p className="intro">Ask the refund agent a question and inspect the payment evidence behind its answer.</p>
    <div className="layout"><form onSubmit={submit}><h2>Query</h2>
      <label htmlFor="scenario">Payment scenario</label><select id="scenario" value={scenario} disabled={busy} onChange={e=>setScenario(e.target.value)}>
        {Object.entries(scenarios).map(([value,label])=><option value={value} key={value}>{label}</option>)}</select>
      <label htmlFor="question">{scenario === "followup" ? "Follow-up question" : "Customer question"}</label>
      <textarea id="question" required maxLength={1200} rows="3" value={question} disabled={busy} onChange={e=>setQuestion(e.target.value)}/>
      <label className="check"><input type="checkbox" checked={evaluate} disabled={busy} onChange={e=>setEvaluate(e.target.checked)}/> Evaluate the reply with OpenAI</label>
      <button disabled={busy}>{busy ? "Running lookup…" : "Run query"}</button>
      <small>Live agent · Simulated payments</small></form>
      <section aria-labelledby="result"><h2 id="result">Agent Lake pipeline</h2><div role="status">{busy ? "Waiting for the refund agent…" : rows.length ? "Lookup complete" : error ? "" : "Run a query to trace the question, tool call, payment evidence, and reply."}</div>
      {saved?.url && <p><a href={saved.url} target="_blank" rel="noreferrer">Open saved LangSmith trace</a></p>}
      {saved?.storage_warning && <p role="status">{saved.storage_warning} Run ID: {saved.run_id}</p>}
      {error && <p role="alert">{error}</p>}
      {rows.map((r,i)=><article key={i}><div className="metadata">{r.refund_id} · Turn {i+1}</div>
        <h3>Agent reply</h3><p className="reply">{r.reply}</p>
        <ol className="pipeline">{r.trace.map(step=><li key={step.stage}>
          <details open={step.stage === "Payment lookup" || step.stage === "Reply evaluation"}>
            <summary>{step.stage}</summary>
            {typeof step.data === "string" ? <p>{step.data}</p> : <pre>{JSON.stringify(step.data,null,2)}</pre>}
          </details></li>)}</ol></article>)}
      </section></div>
      <section className="history"><h2>Saved LangSmith runs</h2>
        <button type="button" onClick={refreshHistory}>Refresh history</button>
        {history.error ? <p role="alert">{history.error}</p> : history.enabled === false
          ? <p>To save new runs, configure LangSmith in the server’s .env and restart the console.</p>
          : history.enabled && !history.runs.length && <p>No saved runs in this project yet.</p>}
        {history.runs?.length > 0 && <ul>{history.runs.map(run=><li key={run.id}>
          <a href={run.url} target="_blank" rel="noreferrer">{run.question}</a>
          <small>{new Date(run.at).toLocaleString()} · {run.status}</small></li>)}</ul>}
      </section></main></>;
}
createRoot(document.getElementById("root")).render(<Console/>);
