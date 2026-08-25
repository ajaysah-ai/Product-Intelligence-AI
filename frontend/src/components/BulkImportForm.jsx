import { useState } from "react";
import { importDataset, orchestrateBatch } from "../api";

export default function BulkImportForm({ onImported, onBatchComplete }) {
  const [file, setFile] = useState(null);
  const [importing, setImporting] = useState(false);
  const [status, setStatus] = useState(null);
  const [importedIds, setImportedIds] = useState([]);
  const [runCount, setRunCount] = useState(5);
  const [running, setRunning] = useState(false);

  const handleImport = async () => {
    if (!file) {
      setStatus({ type: "error", text: "Choose a CSV file first." });
      return;
    }
    setImporting(true);
    setStatus(null);
    setImportedIds([]);
    try {
      const result = await importDataset(file);
      if (result.error) {
        setStatus({ type: "error", text: result.error });
      } else {
        setStatus({ type: "success", text: `Imported ${result.imported_count} rows.` });
        setImportedIds(result.request_ids || []);
        setFile(null);
        onImported();
      }
    } catch (e) {
      setStatus({ type: "error", text: e.message });
    } finally {
      setImporting(false);
    }
  };

  const handleRunBatch = async () => {
    const idsToRun = importedIds.slice(0, runCount);
    if (idsToRun.length === 0) return;
    setRunning(true);
    setStatus({ type: "success", text: `Running enrichment on ${idsToRun.length} rows — this may take a while…` });
    try {
      const result = await orchestrateBatch(idsToRun);
      setStatus({
        type: "success",
        text: `Done: ${result.processed} rows processed (${result.workers_used} workers used). See "Just Processed" below.`,
      });
      onImported();
      if (onBatchComplete) onBatchComplete(idsToRun);
    } catch (e) {
      setStatus({ type: "error", text: e.message });
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="submit-form bulk-import-form">
      <label className="field-label">Bulk import (hackathon CSV)</label>
      <div className="file-input-wrap">
        <input
          className="file-input"
          type="file"
          accept=".csv"
          onChange={(e) => setFile(e.target.files[0] || null)}
        />
      </div>
      {status && <div className={`pipeline-status ${status.type}`}>{status.text}</div>}
      <button className="btn btn-secondary btn-block" onClick={handleImport} disabled={importing}>
        {importing ? "Importing…" : "Import Dataset"}
      </button>

      {importedIds.length > 0 && (
        <div className="batch-run-controls">
          <label className="field-label" style={{ marginTop: 12 }}>
            Run first
          </label>
          <div className="batch-run-row">
            <input
              className="text-input batch-run-count"
              type="number"
              min="1"
              max={importedIds.length}
              value={runCount}
              onChange={(e) => setRunCount(Math.max(1, Math.min(importedIds.length, Number(e.target.value))))}
            />
            <span className="batch-run-label">of {importedIds.length} imported rows</span>
          </div>
          <button className="btn btn-primary btn-block" onClick={handleRunBatch} disabled={running}>
            {running ? "Running…" : "Run Batch Enrichment"}
          </button>
        </div>
      )}
    </div>
  );
}
