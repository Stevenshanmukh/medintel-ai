"use client";

import { useEffect, useState } from "react";

interface HealthResponse {
  status: string;
  db: string;
  pgvector: string;
  error?: string;
}

export default function Home() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    fetch(`${apiUrl}/health`)
      .then((res) => res.json())
      .then((data) => setHealth(data))
      .catch((err) => setError(err.message));
  }, []);

  return (
    <main className="min-h-screen p-8 bg-slate-50">
      <div className="max-w-2xl mx-auto">
        <h1 className="text-3xl font-bold text-slate-900 mb-2">MedIntel AI</h1>
        <p className="text-slate-600 mb-8">Clinical Intelligence System</p>

        <div className="bg-white rounded-lg border border-slate-200 p-6">
          <h2 className="text-lg font-semibold text-slate-900 mb-4">System Status</h2>

          {error && (
            <div className="text-red-600 text-sm">
              Failed to reach backend: {error}
            </div>
          )}

          {health && (
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between">
                <dt className="text-slate-500">Overall</dt>
                <dd className={health.status === "ok" ? "text-green-600" : "text-amber-600"}>
                  {health.status}
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-slate-500">Database</dt>
                <dd className="text-slate-900">{health.db}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-slate-500">pgvector</dt>
                <dd className="text-slate-900">{health.pgvector}</dd>
              </div>
            </dl>
          )}

          {!health && !error && <div className="text-slate-500 text-sm">Checking...</div>}
        </div>
      </div>
    </main>
  );
}
