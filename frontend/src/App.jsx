import { useEffect, useState } from "react";
import { listRequests } from "./api";
import SubmitForm from "./components/SubmitForm";
import BulkImportForm from "./components/BulkImportForm";
import RequestList from "./components/RequestList";
import RequestDetail from "./components/RequestDetail";

export default function App() {
  const [requests, setRequests] = useState([]);
  const [selectedId, setSelectedId] = useState(null);

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

  return (
    <div className="app-shell">
      <div className="sidebar">
        <div className="sidebar-header">
          <div className="brand-mark">Product Intelligence AI</div>
          <div className="brand-title">Catalog Review</div>
        </div>
        <SubmitForm onSubmitted={handleSubmitted} />
        <BulkImportForm onImported={refreshList} />
        <RequestList requests={requests} selectedId={selectedId} onSelect={setSelectedId} />
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
