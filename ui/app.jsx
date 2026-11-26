import React, {useState} from "react";
import {createRoot} from "react-dom/client";

const scenarios = {
  pending: "Pending refund", settled: "Settled refund", failed: "Failed refund",
  timeout: "Processor timeout", missing: "Missing evidence", followup: "Pending → settled (two turns)"
};

function Console() {
  const [scenario, setScenario] = useState("pending");
  const [question, setQuestion] = useState("Has my refund gone through?");
  const [rows, setRows] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    setRows([]);
    try {
      const response = await fetch("/api/query", {method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({case: scenario, question})});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Request failed. Try again.");
      setRows(data.turns);
    } catch (e) {
      setError(e instanceof TypeError ? "Could not reach the local server. Check the connection and retry." : e.message);
    } finally {
      setBusy(false);
    }
  }
  return <><header><div className="brand"><span aria-hidden="true">≋</span> Agent Lake</div></header>
    <main><h1>Refund console</h1><p className="intro">Ask the refund agent a question and inspect the payment evidence behind its answer.</p>
    <div className="layout"><form onSubmit={submit}><h2>Query</h2>
      <label htmlFor="scenario">Payment scenario</label><select id="scenario" value={scenario} disabled={busy} onChange={e=>setScenario(e.target.value)}>
        {Object.entries(scenarios).map(([value,label])=><option value={value} key={value}>{label}</option>)}</select>
      <label htmlFor="question">{scenario === "followup" ? "Follow-up question" : "Customer question"}</label>
      <textarea id="question" required maxLength={1200} rows="3" value={question} disabled={busy} onChange={e=>setQuestion(e.target.value)}/>
      <button disabled={busy}>{busy ? "Running lookup…" : "Run query"}</button>
      <small>Live agent · Simulated payments</small></form>
      <section aria-labelledby="result"><h2 id="result">Result</h2><div role="status">{busy ? "Waiting for the refund agent…" : rows.length ? "Lookup complete" : error ? "" : "Run a query to see the agent’s reply and lookup result."}</div>
      {error && <p role="alert">{error}</p>}
      {rows.map((r,i)=><article key={i}><div className="metadata">{r.refund_id} · Turn {i+1}</div>
        <h3>Customer</h3><p>{r.question}</p><h3>Agent reply</h3><p className="reply">{r.reply}</p>
        <details open><summary>Payment lookup</summary><pre>{JSON.stringify(r.tool_result,null,2)}</pre></details></article>)}
      </section></div></main></>;
}
createRoot(document.getElementById("root")).render(<Console/>);
