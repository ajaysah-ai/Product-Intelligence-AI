import { useState } from "react";
import { submitRequest } from "../api";

const SOURCES = [
  { key: "website", label: "Website" },
  { key: "catalog", label: "Catalog" },
  { key: "tech_doc", label: "Tech Doc" },
  { key: "digital_asset", label: "Digital Asset" },
];

export default function SubmitForm({ onSubmitted }) {
  const [text, setText] = useState("");
  const [files, setFiles] = useState([]);
  const [sources, setSources] = useState(() => new Set(SOURCES.map((s) => s.key)));
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const toggleSource = (key) => {
    setSources((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const handleSubmit = async () => {
    if (!text.trim() && files.length === 0) {
      setError("Enter a description or attach a file.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const result = await submitRequest({ text, files, sourcesSelected: Array.from(sources) });
      if (result.error) {
        setError(result.error);
      } else {
        setText("");
        setFiles([]);
        onSubmitted(result.request_id);
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="submit-form">
      <label className="field-label">New request</label>
      <textarea
        className="textarea-input"
        placeholder="Product description, part number, or notes..."
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <div className="file-input-wrap">
        <input
          className="file-input"
          type="file"
          multiple
          onChange={(e) => setFiles(Array.from(e.target.files))}
        />
      </div>

      <label className="field-label" style={{ marginTop: 14 }}>
        Sources to enable
      </label>
      <div className="source-toggle-list">
        {SOURCES.map((s) => (
          <label key={s.key} className="source-toggle">
            <input
              type="checkbox"
              checked={sources.has(s.key)}
              onChange={() => toggleSource(s.key)}
            />
            {s.label}
          </label>
        ))}
      </div>

      {error && <div className="pipeline-status error">{error}</div>}
      <button className="btn btn-primary btn-block" onClick={handleSubmit} disabled={submitting}>
        {submitting ? "Submitting…" : "Submit"}
      </button>
    </div>
  );
}
