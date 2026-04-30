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

export interface StructuredEvidenceRow {
  // Week 3 paths (current_medications, first_occurrence, all_mentions)
  visit_date: string | null;
  entity_text: string | null;
  normalized_text: string | null;
  entity_type: string | null;
  negated: boolean | null;
  last_visit: string | null;
  visit_id: string | null;

  // compare_visits diff payload
  category: string | null;          // "medication" | "symptom"
  diff_status: string | null;       // "added" | "removed" | "new" | "resolved"
  name: string | null;
  visit_a: string | null;
  visit_b: string | null;

  // trend_over_time series payload
  chief_complaint: string | null;
  present: boolean | null;
  status: string | null;            // "affirmed" | "denied" | "absent"
  severity: string | null;
  matched_entities: string[] | null;
}

export type QueryPath = "rag" | "structured" | "refused";

export interface QueryResponse {
  question: string;
  answer: string;
  intent: string;
  path: QueryPath;
  chunks: RetrievedChunk[];
  structured_evidence: StructuredEvidenceRow[];
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
  k: number = 5,
  matchMode: "loose" | "strict" = "loose"
): Promise<QueryResponse> {
  const res = await fetch(`${API_URL}/api/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      patient_id: patientId,
      k,
      match_mode: matchMode,
    }),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Query failed: ${res.status} - ${err}`);
  }
  return res.json();
}

// --- Timeline types ---

export interface VisitEntities {
  medications_affirmed: string[];
  symptoms_affirmed: string[];
  symptoms_denied: string[];
}

export interface VisitTimelineEntry {
  visit_id: string;
  visit_number: number;
  visit_date: string;
  chief_complaint: string | null;
  raw_transcript: string;
  entities: VisitEntities;
}

export interface PatientHeader {
  id: string;
  name: string;
  mrn: string | null;
}

export interface PatientVisitsResponse {
  patient: PatientHeader;
  visits: VisitTimelineEntry[];
}

export async function getPatientVisits(
  patientId: string
): Promise<PatientVisitsResponse> {
  const res = await fetch(`${API_URL}/api/patients/${patientId}/visits`);
  if (!res.ok) {
    throw new Error(`Failed to fetch visits: ${res.status}`);
  }
  return res.json();
}

// --- Trend chart helpers ---

export interface TrendableSubjects {
  symptoms: string[];
  medications: string[];
}

/**
 * Walk the visit list and return subjects (symptoms + medications) that
 * appear in 2 or more visits. Counts a subject's appearance per visit
 * regardless of affirmed/denied status — for the chart, what matters is
 * whether the topic was discussed, not its valence.
 *
 * Symptoms count if they appear in either affirmed OR denied for that visit.
 * Medications only count when affirmed (negated medications are usually
 * "not on this drug" rather than "discontinued today").
 */
export function getTrendableSubjects(
  visits: VisitTimelineEntry[]
): TrendableSubjects {
  const symptomCounts = new Map<string, number>();
  const medicationCounts = new Map<string, number>();

  for (const visit of visits) {
    // Symptom counts: union of affirmed and denied for this visit
    const symptomsThisVisit = new Set<string>([
      ...visit.entities.symptoms_affirmed,
      ...visit.entities.symptoms_denied,
    ]);
    for (const s of symptomsThisVisit) {
      symptomCounts.set(s, (symptomCounts.get(s) ?? 0) + 1);
    }

    // Medication counts: affirmed only
    for (const m of visit.entities.medications_affirmed) {
      medicationCounts.set(m, (medicationCounts.get(m) ?? 0) + 1);
    }
  }

  const symptoms = [...symptomCounts.entries()]
    .filter(([, count]) => count >= 2)
    .map(([name]) => name)
    .sort();

  const medications = [...medicationCounts.entries()]
    .filter(([, count]) => count >= 2)
    .map(([name]) => name)
    .sort();

  return { symptoms, medications };
}

// --- Risk alerts ---

export interface RiskFinding {
  detector: string;
  severity: "low" | "moderate" | "high" | string;
  title: string;
  summary: string;
  evidence: Record<string, unknown>;
}

export interface RiskAlertsResponse {
  patient: PatientHeader;
  findings: RiskFinding[];
  severity_counts: {
    high: number;
    moderate: number;
    low: number;
  };
  total_visits: number;
}

export async function getPatientRiskAlerts(
  patientId: string
): Promise<RiskAlertsResponse> {
  const res = await fetch(`${API_URL}/api/patients/${patientId}/risk_alerts`);
  if (!res.ok) {
    throw new Error(`Failed to fetch risk alerts: ${res.status}`);
  }
  return res.json();
}
