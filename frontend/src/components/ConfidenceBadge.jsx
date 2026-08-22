export default function ConfidenceBadge({ value }) {
  if (value === null || value === undefined) return null;
  const level = value >= 75 ? "high" : value >= 50 ? "medium" : "low";
  return <span className={`confidence-badge ${level}`}>{value}%</span>;
}
