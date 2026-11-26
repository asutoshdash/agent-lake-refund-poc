import React, {useState, useEffect} from "react";
import {createRoot} from "react-dom/client";

const scenarios = {
  pending: "Pending refund", settled: "Settled refund", failed: "Failed refund",
  timeout: "Processor timeout", missing: "Missing evidence", followup: "Pending → settled (two turns)"
};

function SavedTrace({id}) {
  const [run, setRun] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    let timer;
    async function read() {
      try {
        const response = await fetch("/api/runs/" + id, {signal: controller.signal});
        if (!response.ok) throw new Error("Could not load this trace.");
        const data = await response.json();
        setRun(data);
        if (data.status === "Running") timer = setTimeout(read, 1200);
      } catch (e) {
        if (!controller.signal.aborted) setError(e.message);
      }
    }
    read();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [id]);
  if (error) return <p role="alert">{error}</p>;
  if (!run) return <p role="status">Loading saved trace…</p>;
  return <article><h3>{run.question}</h3><small>{scenarios[run.scenario]} · {run.status}</small>
    <ol className="pipeline">{run.events.map((event, index)=><li key={index}>
      <details open={event.stage === "Payment lookup"}><summary>Turn {event.turn} · {event.stage}</summary>
        <small>{event.at}</small><pre>{typeof event.data === "string" ? event.data : JSON.stringify(event.data,null,2)}</pre>
      </details></li>)}</ol></article>;
}

function Console() {
  const [scenario, setScenario] = useState("pending");
  const [question, setQuestion] = useState("Has my refund gone through?");
  const [rows, setRows] = useState([]);
  const [evaluate, setEvaluate] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const [history, setHistory] = useState({runs: []});
  const [selected, setSelected] = useState(null);

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
    setSelected(null);
    try {
      const response = await fetch("/api/query", {method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({case: scenario, question, evaluate})});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Request failed. Try again.");
      setRows(data.turns);

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
      {error && <p role="alert">{error}</p>}
      {rows.map((r,i)=><article key={i}><div className="metadata">{r.refund_id} · Turn {i+1}</div>
        <h3>Agent reply</h3><p className="reply">{r.reply}</p>
        <ol className="pipeline">{r.trace.map(step=><li key={step.stage}>
          <details open={step.stage === "Payment lookup" || step.stage === "Reply evaluation"}>
            <summary>{step.stage}</summary>
            {typeof step.data === "string" ? <p>{step.data}</p> : <pre>{JSON.stringify(step.data,null,2)}</pre>}
          </details></li>)}</ol></article>)}
      </section></div>
      <section className="history"><h2>Saved runs</h2><small>SQLite · Latest 20 runs</small>
        <button type="button" onClick={refreshHistory}>Refresh history</button>
        {history.error && <p role="alert">{history.error}</p>}
        {history.runs?.length === 0 && <p>No saved runs yet.</p>}
        {history.runs?.length > 0 && <ul>{history.runs.map(run=><li key={run.id}>
          <button type="button" aria-expanded={selected === run.id}
            onClick={()=>setSelected(selected === run.id ? null : run.id)}>{run.question}</button>
          <small>{new Date(run.at).toLocaleString()} · {run.status}</small>
          {selected === run.id && <SavedTrace key={run.id} id={run.id}/>}</li>)}</ul>}
      </section></main></>;
}
createRoot(document.getElementById("root")).render(<Console/>);
