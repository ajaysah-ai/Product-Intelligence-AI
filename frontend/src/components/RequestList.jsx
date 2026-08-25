function RequestItem({ r, selectedId, onSelect }) {
  return (
    <div
      className={`request-item ${r.request_id === selectedId ? "active" : ""}`}
      onClick={() => onSelect(r.request_id)}
    >
      <div className="request-item-title">{r.mfg_part_num || r.user_text || "(untitled)"}</div>
      <div className="request-item-meta">
        <span className={`status-dot ${r.has_draft ? "has-draft" : "pending"}`} />
        {r.has_draft ? "draft ready" : r.status}
      </div>
    </div>
  );
}

export default function RequestList({ requests, selectedId, onSelect, recentBatchIds }) {
  if (!requests.length) {
    return <div className="request-list-empty">No requests yet — submit one above.</div>;
  }

  const recentSet = recentBatchIds || new Set();
  const recentItems = requests.filter((r) => recentSet.has(r.request_id));
  const otherItems = requests.filter((r) => !recentSet.has(r.request_id));

  return (
    <div className="request-list">
      {recentItems.length > 0 && (
        <>
          <div className="request-list-section-label">Just Processed ({recentItems.length})</div>
          {recentItems.map((r) => (
            <RequestItem key={r.request_id} r={r} selectedId={selectedId} onSelect={onSelect} />
          ))}
          <div className="request-list-section-label">All Requests</div>
        </>
      )}
      {otherItems.map((r) => (
        <RequestItem key={r.request_id} r={r} selectedId={selectedId} onSelect={onSelect} />
      ))}
    </div>
  );
}
