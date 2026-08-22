export default function RequestList({ requests, selectedId, onSelect }) {
  if (!requests.length) {
    return <div className="request-list-empty">No requests yet — submit one above.</div>;
  }

  return (
    <div className="request-list">
      {requests.map((r) => (
        <div
          key={r.request_id}
          className={`request-item ${r.request_id === selectedId ? "active" : ""}`}
          onClick={() => onSelect(r.request_id)}
        >
          <div className="request-item-title">
            {r.mfg_part_num || r.user_text || "(untitled)"}
          </div>
          <div className="request-item-meta">
            <span className={`status-dot ${r.has_draft ? "has-draft" : "pending"}`} />
            {r.has_draft ? "draft ready" : r.status}
          </div>
        </div>
      ))}
    </div>
  );
}
