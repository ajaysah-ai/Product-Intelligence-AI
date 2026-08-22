import { useEffect, useState } from "react";
import { approveRequest, getRequestDetail, runChunkAndEmbed, runExtract, runOrchestrate } from "../api";
import ConfidenceBadge from "./ConfidenceBadge";
import SourcesPanel from "./SourcesPanel";

export default function RequestDetail({ requestId, onApproved }) {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [pipelineStatus, setPipelineStatus] = useState(null);
  const [running, setRunning] = useState(false);
  const [approving, setApproving] = useState(false);
  const [approved, setApproved] = useState(null);

  const [title, setTitle] = useState("");
  const [manufacturerName, setManufacturerName] = useState("");
  const [specs, setSpecs] = useState([]);
  const [features, setFeatures] = useState([]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setApproved(null);
    setPipelineStatus(null);
    getRequestDetail(requestId).then((d) => {
      if (cancelled) return;
      setDetail(d);
      if (d.draft) {
        setTitle(d.draft.title || "");
        setManufacturerName(d.draft.manufacturer_name || "");
        setSpecs(d.draft.specs || []);
        setFeatures(d.draft.features || []);
      } else {
        setTitle("");
        setManufacturerName("");
        setSpecs([]);
        setFeatures([]);
      }
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [requestId]);

  const runPipeline = async () => {
    setRunning(true);
    setPipelineStatus("Extracting uploaded files…");
    try {
      await runExtract(requestId);
      setPipelineStatus("Chunking and embedding…");
      await runChunkAndEmbed(requestId);
      setPipelineStatus("Running Supervisor + sub-agents…");
      const result = await runOrchestrate(requestId);
      if (result.guardrail_blocked) {
        setPipelineStatus(`Blocked by guardrails: ${result.guardrail_reason}`);
        setRunning(false);
        return;
      }
      const fresh = await getRequestDetail(requestId);
      setDetail(fresh);
      if (fresh.draft) {
        setTitle(fresh.draft.title || "");
        setManufacturerName(fresh.draft.manufacturer_name || "");
        setSpecs(fresh.draft.specs || []);
        setFeatures(fresh.draft.features || []);
      }
      setPipelineStatus("Draft ready for review.");
    } catch (e) {
      setPipelineStatus(`Error: ${e.message}`);
    } finally {
      setRunning(false);
    }
  };

  const updateSpec = (index, field, value) => {
    setSpecs((prev) => prev.map((s, i) => (i === index ? { ...s, [field]: value } : s)));
  };

  const removeSpec = (index) => {
    setSpecs((prev) => prev.filter((_, i) => i !== index));
  };

  const addSpec = () => {
    setSpecs((prev) => [...prev, { key: "", value: "", uom: "", confidence: null }]);
  };

  const handleApprove = async () => {
    setApproving(true);
    try {
      const overrides = {
        title,
        manufacturer_name: manufacturerName,
        specs: specs.filter((s) => s.key && s.value).map((s) => ({ key: s.key, value: s.value, unit: s.uom })),
        features: features.map((f) => f.value),
      };
      const result = await approveRequest(requestId, overrides);
      if (result.error) {
        setPipelineStatus(`Approve failed: ${result.error}`);
      } else {
        setApproved(result);
        onApproved && onApproved();
      }
    } catch (e) {
      setPipelineStatus(`Approve failed: ${e.message}`);
    } finally {
      setApproving(false);
    }
  };

  const handleReject = () => {
    // Purely a UI reset — no API call is made, so nothing is ever written
    // to the Main DB unless Approve is explicitly clicked.
    setDetail((d) => ({ ...d, draft: null }));
    setSpecs([]);
    setFeatures([]);
    setPipelineStatus("Draft discarded (nothing was saved).");
  };

  if (loading) return <div className="empty-state">Loading…</div>;
  if (!detail) return <div className="empty-state">Request not found.</div>;

  return (
    <div>
      {approved && (
        <div className="approved-banner">
          Approved — product <strong>{approved.product_id}</strong> is now in the Main DB.
        </div>
      )}

      <div className="detail-header">
        <div className="detail-part-num">{detail.mfg_part_num || "—"}</div>
        <div className="detail-part-desc">{detail.part_desc || detail.user_text}</div>
        {(detail.e1_brand || detail.unilog_brand || detail.part_manuf) && (
          <div className="brand-chips">
            {detail.e1_brand && <span className="brand-chip">{detail.e1_brand}</span>}
            {detail.part_manuf && <span className="brand-chip">{detail.part_manuf}</span>}
          </div>
        )}
        <div className="source-badges">
          {["website", "catalog", "tech_doc", "digital_asset"].map((s) => (
            <span key={s} className={`source-badge ${detail.sources_selected?.includes(s) ? "enabled" : ""}`}>
              {s.replace("_", " ")}
            </span>
          ))}
        </div>
      </div>

      {!detail.draft && (
        <div className="section">
          <button className="btn btn-primary" onClick={runPipeline} disabled={running}>
            {running ? "Running…" : "Run Enrichment"}
          </button>
          {pipelineStatus && <div className="pipeline-status">{pipelineStatus}</div>}
        </div>
      )}

      {detail.draft && !approved && (
        <>
          <SourcesPanel provenance={detail.draft.agent_provenance || {}} />

          <div className="section">
            <div className="section-title">Product</div>
            <div className="editable-field-row">
              <label className="editable-field-label">Title</label>
              <input className="editable-field-input" value={title} onChange={(e) => setTitle(e.target.value)} />
            </div>
            <div className="editable-field-row">
              <label className="editable-field-label">Manufacturer</label>
              <input
                className="editable-field-input"
                value={manufacturerName}
                onChange={(e) => setManufacturerName(e.target.value)}
              />
            </div>
          </div>

          <div className="section">
            <div className="section-title">Specifications</div>
            {specs.length === 0 ? (
              <div className="empty-note">No specs extracted.</div>
            ) : (
              <table className="spec-table">
                <thead>
                  <tr>
                    <th style={{ width: "26%" }}>Key</th>
                    <th style={{ width: "26%" }}>Value</th>
                    <th style={{ width: "12%" }}>Unit</th>
                    <th style={{ width: "14%" }}>Confidence</th>
                    <th style={{ width: "14%" }}>Validation</th>
                    <th style={{ width: "8%" }}></th>
                  </tr>
                </thead>
                <tbody>
                  {specs.map((s, i) => (
                    <tr key={i}>
                      <td>
                        <input
                          className="spec-cell-input"
                          value={s.key || ""}
                          onChange={(e) => updateSpec(i, "key", e.target.value)}
                        />
                      </td>
                      <td>
                        <input
                          className="spec-cell-input"
                          value={s.value || ""}
                          onChange={(e) => updateSpec(i, "value", e.target.value)}
                        />
                      </td>
                      <td>
                        <input
                          className="spec-cell-input"
                          value={s.uom || ""}
                          onChange={(e) => updateSpec(i, "uom", e.target.value)}
                        />
                      </td>
                      <td>
                        <ConfidenceBadge value={s.confidence} />
                      </td>
                      <td>
                        {s.conflicts && s.conflicts.length > 0 ? (
                          <span
                            className="conflict-flag"
                            title={s.conflicts
                              .map((c) => `${c.source_type}: new "${c.new_value}" vs existing "${c.existing_value}"`)
                              .join("\n")}
                          >
                            ⚠ conflict
                          </span>
                        ) : (
                          <span className="validation-ok">✓ no conflict</span>
                        )}
                      </td>
                      <td>
                        <button className="spec-remove-btn" onClick={() => removeSpec(i)} title="Remove">
                          ×
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <button className="btn btn-secondary" style={{ marginTop: 10 }} onClick={addSpec}>
              + Add spec
            </button>
          </div>

          {pipelineStatus && <div className="pipeline-status">{pipelineStatus}</div>}

          <div className="action-bar">
            <button className="btn btn-primary" onClick={handleApprove} disabled={approving}>
              {approving ? "Approving…" : "Approve"}
            </button>
            <button className="btn btn-danger" onClick={handleReject} disabled={approving}>
              Reject
            </button>
          </div>
        </>
      )}
    </div>
  );
}
