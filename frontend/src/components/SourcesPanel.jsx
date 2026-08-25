import ConfidenceBadge from "./ConfidenceBadge";

const SOURCE_LABELS = {
  website: "Website",
  catalog: "Catalog",
  tech_doc: "Tech Doc",
  digital_asset: "Digital Asset",
};

function originCounts(origins) {
  const request = origins.filter((o) => o === "request").length;
  const mainDb = origins.filter((o) => o === "main_db").length;
  return { request, mainDb };
}

export default function SourcesPanel({ provenance }) {
  const sourceKeys = Object.keys(SOURCE_LABELS);
  const ranAny = sourceKeys.some((k) => provenance[k]);

  if (!ranAny) {
    return (
      <div className="section">
        <div className="section-title">Sources</div>
        <div className="empty-note">No agents ran for this request yet.</div>
      </div>
    );
  }

  return (
    <div className="section">
      <div className="section-title">Sources — where this data came from</div>
      <div className="sources-panel">
        {sourceKeys.map((key) => {
          const info = provenance[key];
          const label = SOURCE_LABELS[key];

          if (!info) {
            return (
              <div key={key} className="source-row source-row-inactive">
                <span className="source-row-label">{label}</span>
                <span className="source-row-status">not enabled for this request</span>
              </div>
            );
          }

          if (info.error) {
            return (
              <div key={key} className="source-row source-row-error">
                <span className="source-row-label">{label}</span>
                <span className="source-row-status">Error: {info.error}</span>
              </div>
            );
          }

          const { request, mainDb } = originCounts(info.retrieved_origins || []);

          return (
            <div key={key} className="source-row">
              <div className="source-row-top">
                <span className="source-row-label">{label}</span>
                <ConfidenceBadge value={info.confidence} />
              </div>

              {info.used_url ? (
                <div className="source-row-url">
                  <a href={info.used_url} target="_blank" rel="noreferrer">
                    {info.used_url}
                  </a>
                  <span className={`url-origin-tag ${info.discovered_via_search ? "found" : "given"}`}>
                    {info.discovered_via_search ? "found via search" : "provided URL"}
                  </span>
                </div>
              ) : (
                <div className="source-row-url source-row-url-none">
                  No external URL fetched — used existing content only
                </div>
              )}

              <div className="source-row-detail">
                {info.retrieved_count} chunk{info.retrieved_count === 1 ? "" : "s"} retrieved
                {info.retrieved_count > 0 && (
                  <>
                    {" "}
                    ({request} from this request, {mainDb} from Main DB)
                  </>
                )}
                {info.conflicts && info.conflicts.length > 0 && (
                  <span className="conflict-flag" style={{ marginLeft: 8 }}>
                    ⚠ {info.conflicts.length} conflict{info.conflicts.length === 1 ? "" : "s"} vs Main DB
                  </span>
                )}
                {info.normalize_method && info.normalize_method !== "llm" && (
                  <span
                    className="conflict-flag"
                    style={{ marginLeft: 8 }}
                    title={info.normalize_method}
                  >
                    ⚠ LLM not used ({info.normalize_method.startsWith("heuristic_fallback_llm_error") ? "LLM call failed" : "no API key"})
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
