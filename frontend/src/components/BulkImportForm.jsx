import { useState } from "react";
import { importDataset } from "../api";

export default function BulkImportForm({ onImported }) {
  const [file, setFile] = useState(null);
  const [importing, setImporting] = useState(false);
  const [status, setStatus] = useState(null);

  const handleImport = async () => {
    if (!file) {
      setStatus({ type: "error", text: "Choose a CSV file first." });
      return;
    }
    setImporting(true);
    setStatus(null);
    try {
      const result = await importDataset(file);
      if (result.error) {
        setStatus({ type: "error", text: result.error });
      } else {
        setStatus({ type: "success", text: `Imported ${result.imported_count} rows.` });
        setFile(null);
        onImported();
      }
    } catch (e) {
      setStatus({ type: "error", text: e.message });
    } finally {
      setImporting(false);
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
    </div>
  );
}
