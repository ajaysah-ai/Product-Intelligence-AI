import { useEffect, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export default function App() {
  const [status, setStatus] = useState("checking...");
  const [dbStatus, setDbStatus] = useState("checking...");

  useEffect(() => {
    const poll = async () => {
      try {
        const res = await fetch(`${API_BASE}/health`);
        const data = await res.json();
        setStatus(data.status);
      } catch {
        setStatus("unreachable");
      }

      try {
        const res = await fetch(`${API_BASE}/health/db`);
        const data = await res.json();
        setDbStatus(data.status);
      } catch {
        setDbStatus("unreachable");
      }
    };

    poll();
    const interval = setInterval(poll, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div style={{ fontFamily: "sans-serif", padding: "2rem" }}>
      <h1>Product Intelligence AI</h1>
      <p>Backend status: <strong>{status}</strong></p>
      <p>Database status: <strong>{dbStatus}</strong></p>
    </div>
  );
}
