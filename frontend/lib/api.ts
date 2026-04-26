const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface Patient {
  id: string;
  name: string;
  mrn: string | null;
  visit_count: number;
}

export interface RetrievedChunk {
  chunk_id: string;
  visit_id: string;
  visit_date: string;
  chunk_index: number;
  chunk_text: string;
  similarity: number;
}

export interface QueryResponse {
  question: string;
  answer: string;
  chunks: RetrievedChunk[];
  model: string;
  latency_ms: number;
}

export async function listPatients(): Promise<Patient[]> {
  const res = await fetch(`${API_URL}/api/patients`);
  if (!res.ok) throw new Error(`Failed to list patients: ${res.status}`);
  return res.json();
}

export async function runQuery(
  question: string,
  patientId: string | null,
  k: number = 5
): Promise<QueryResponse> {
  const res = await fetch(`${API_URL}/api/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, patient_id: patientId, k }),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Query failed: ${res.status} - ${err}`);
  }
  return res.json();
}
