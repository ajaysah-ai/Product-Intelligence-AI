import { useRef, useState } from "react";
import { importDataset, orchestrateBatch } from "../api";

export default function BulkImportForm({ onImported, onBatchComplete }) {
  const fileInputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [importing, setImporting] = useState(false);
  const [status, setStatus] = useState(null);
  const [importedIds, setImportedIds] = useState([]);
  const [fromRow, setFromRow] = useState(1);
  const [toRow, setToRow] = useState(5);
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
        setToRow(Math.min(5, result.imported_count || 5));
        setFile(null);
        if (fileInputRef.current) fileInputRef.current.value = ""; // native input doesn't clear from React state alone
        onImported();
      }
    } catch (e) {
      setStatus({ type: "error", text: e.message });
    } finally {
      setImporting(false);
    }
  };

  const handleRunBatch = async () => {
    // fromRow/toRow are 1-indexed and inclusive, as shown to the user
    const idsToRun = importedIds.slice(fromRow - 1, toRow);
    if (idsToRun.length === 0) return;

    setRunning(true);
    setStatus({ type: "success", text: `Running enrichment on rows ${fromRow}–${toRow} — this may take a while…` });
    try {
      const result = await orchestrateBatch(idsToRun);
      const succeeded = (result.results || []).filter((r) => !r.error && r.detected_product_id);
      const failed = (result.results || []).filter((r) => r.error);

      if (failed.length > 0) {
        setStatus({
          type: failed.length === idsToRun.length ? "error" : "success",
          text:
            `${succeeded.length} succeeded, ${failed.length} FAILED — ` +
            `most likely the database was reset since you imported (rebuild/restart) and these row IDs no longer exist. ` +
            `Reload the page and re-import the CSV. First failure: ${failed[0].error}`,
        });
      } else {
        setStatus({
          type: "success",
          text: `Done: ${succeeded.length} rows processed successfully (${result.workers_used} workers used). See "Just Processed" below.`,
        });
      }

      onImported();
      const succeededIds = succeeded.map((r) => r.request_id);
      if (onBatchComplete && succeededIds.length > 0) onBatchComplete(succeededIds);
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
          ref={fileInputRef}
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
            Row range to run ({importedIds.length} imported)
          </label>
          <div className="batch-run-row">
            <span className="batch-run-label">From</span>
            <input
              className="text-input batch-run-count"
              type="number"
              min="1"
              max={importedIds.length}
              value={fromRow}
              onChange={(e) => setFromRow(Math.max(1, Math.min(importedIds.length, Number(e.target.value))))}
            />
            <span className="batch-run-label">To</span>
            <input
              className="text-input batch-run-count"
              type="number"
              min="1"
              max={importedIds.length}
              value={toRow}
              onChange={(e) => setToRow(Math.max(1, Math.min(importedIds.length, Number(e.target.value))))}
            />
          </div>
          {fromRow > toRow && <div className="pipeline-status error">"From" must be ≤ "To".</div>}
          <button
            className="btn btn-primary btn-block"
            onClick={handleRunBatch}
            disabled={running || fromRow > toRow}
          >
            {running ? "Running…" : `Run Batch Enrichment (${Math.max(0, toRow - fromRow + 1)} rows)`}
          </button>
        </div>
      )}
    </div>
  );
}
