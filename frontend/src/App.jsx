import { useEffect, useState } from "react";
import { exportAllCsv, listRequests } from "./api";
import SubmitForm from "./components/SubmitForm";
import BulkImportForm from "./components/BulkImportForm";
import RequestList from "./components/RequestList";
import RequestDetail from "./components/RequestDetail";

export default function App() {
  const [requests, setRequests] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [recentBatchIds, setRecentBatchIds] = useState(new Set());
  const [exporting, setExporting] = useState(false);
  const [exportStatus, setExportStatus] = useState(null);

  const refreshList = async () => {
    const result = await listRequests();
    setRequests(result.requests || []);
  };

  useEffect(() => {
    refreshList();
  }, []);

  const handleSubmitted = async (requestId) => {
    await refreshList();
    setSelectedId(requestId);
  };

  const handleBatchComplete = async (processedIds) => {
    setRecentBatchIds(new Set(processedIds));
    await refreshList();
    if (processedIds.length > 0) {
      setSelectedId(processedIds[0]); // jump straight to a result, don't make them hunt for it
    }
  };

  const handleExportAll = async () => {
    setExporting(true);
    setExportStatus(null);
    try {
      const result = await exportAllCsv();
      setExportStatus(`Downloaded ${result.rowCount ?? "?"} approved products.`);
    } catch (e) {
      setExportStatus(`Export failed: ${e.message}`);
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="app-shell">
      <div className="sidebar">
        <div className="sidebar-header">
          <div className="brand-mark">Product Intelligence AI</div>
          <div className="brand-title">Catalog Review</div>
        </div>
        <SubmitForm onSubmitted={handleSubmitted} />
        <BulkImportForm onImported={refreshList} onBatchComplete={handleBatchComplete} />
        <RequestList requests={requests} selectedId={selectedId} onSelect={setSelectedId} recentBatchIds={recentBatchIds} />
        <div className="export-all-footer">
          <button className="btn btn-primary btn-block" onClick={handleExportAll} disabled={exporting}>
            {exporting ? "Exporting…" : "Export All Approved (CSV)"}
          </button>
          {exportStatus && <div className="pipeline-status">{exportStatus}</div>}
        </div>
      </div>
      <div className="main-panel">
        {selectedId ? (
          <RequestDetail requestId={selectedId} onApproved={refreshList} />
        ) : (
          <div className="empty-state">Select a request, or submit a new one to get started.</div>
        )}
      </div>
    </div>
  );
}
