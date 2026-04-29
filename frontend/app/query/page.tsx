"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import {
  listPatients,
  runQuery,
  type Patient,
  type QueryResponse,
  type StructuredEvidenceRow,
} from "@/lib/api";
import { CompareEvidence } from "@/components/compare-evidence";
import {
  TrendChartView,
  TrendPoint,
  extractFindingNote,
  evidenceRowsToPoints,
} from "@/components/trend-chart-view";

const PATH_LABELS: Record<string, { label: string; tone: string }> = {
  structured: { label: "Structured query", tone: "bg-blue-100 text-blue-900 border-blue-200" },
  rag: { label: "RAG synthesis", tone: "bg-violet-100 text-violet-900 border-violet-200" },
  refused: { label: "Refused", tone: "bg-amber-100 text-amber-900 border-amber-200" },
};

const INTENT_LABELS: Record<string, string> = {
  current_medications: "Current medications",
  first_occurrence: "First occurrence",
  all_mentions: "All mentions",
  narrative_synthesis: "Narrative synthesis",
  compare_visits: "Compare visits",
  trend_over_time: "Trend over time",
  unanswerable_or_unsafe: "Unsafe / out of scope",
};

const SAMPLE_QUERIES = [
  "What medications is Sarah Chen currently taking?",
  "When did chest pain first appear?",
  "List every visit where she mentioned shortness of breath",
  "Compare her first and most recent visit",
  "How has her chest pain progressed?",
  "How have her symptoms progressed over time?",
  "Should she stop taking her metoprolol?",
];

export default function QueryPage() {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [selectedPatient, setSelectedPatient] = useState<string | null>(null);
  const [question, setQuestion] = useState(SAMPLE_QUERIES[0]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<QueryResponse | null>(null);

  useEffect(() => {
    listPatients()
      .then((ps) => {
        setPatients(ps);
        if (ps.length > 0) setSelectedPatient(ps[0].id);
      })
      .catch((e) => setError(e.message));
  }, []);

  const handleSubmit = async () => {
    if (!question.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await runQuery(question, selectedPatient, 5);
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen p-6 bg-slate-50">
      <div className="max-w-6xl mx-auto">
        <div className="mb-6">
          <h1 className="text-3xl font-bold text-slate-900">Clinical Query</h1>
          <p className="text-slate-600 mt-1">
            Hybrid retrieval: structured queries for facts and timelines, RAG for narrative
            synthesis, refusal for clinical advice. Same endpoint, intent-routed.
          </p>
        </div>

        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="text-base">Ask a question</CardTitle>
            <CardDescription>
              {patients.length > 0
                ? `Querying: ${patients.find((p) => p.id === selectedPatient)?.name ?? "—"}`
                : "Loading patients..."}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="What has the patient reported?"
              rows={3}
              className="resize-none"
            />

            <div className="flex flex-wrap gap-2">
              {SAMPLE_QUERIES.map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() => setQuestion(q)}
                  className="text-xs px-2 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded border border-slate-200 transition"
                >
                  {q}
                </button>
              ))}
            </div>

            <div className="flex justify-between items-center">
              <div className="text-xs text-slate-500">
                {result && (
                  <>
                    Last query: {result.latency_ms}ms · model {result.model}
                  </>
                )}
              </div>
              <Button onClick={handleSubmit} disabled={loading || !selectedPatient}>
                {loading ? "Thinking..." : "Submit"}
              </Button>
            </div>
            {error && (
              <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded p-3">
                {error}
              </div>
            )}
          </CardContent>
        </Card>

        {result && <ResultPanel result={result} />}
      </div>
    </main>
  );
}

function ResultPanel({ result }: { result: QueryResponse }) {
  const pathMeta = PATH_LABELS[result.path] ?? PATH_LABELS.rag;
  const intentLabel = INTENT_LABELS[result.intent] ?? result.intent;

  // Longitudinal intents get a stacked layout — answer on top, evidence
  // (with dedicated visual treatment) below — because the diff grid and
  // the chart both need horizontal space.
  const isLongitudinal =
    result.intent === "compare_visits" || result.intent === "trend_over_time";

  if (isLongitudinal) {
    return (
      <div className="space-y-6">
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <Badge className={`${pathMeta.tone} border`}>{pathMeta.label}</Badge>
              <Badge variant="outline">{intentLabel}</Badge>
            </div>
            <CardTitle className="text-base mt-1">Answer</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="prose prose-sm max-w-none whitespace-pre-wrap text-slate-800">
              {result.answer}
            </div>
          </CardContent>
        </Card>

        {result.intent === "compare_visits" && (
          <CompareEvidence rows={result.structured_evidence} answer={result.answer} />
        )}

        {result.intent === "trend_over_time" && (
          <TrendChartView
            points={evidenceRowsToPoints(result.structured_evidence)}
            findingNote={extractFindingNote(result.answer)}
            title="Trend over time"
            description="Mentions per visit, color-coded by status"
          />
        )}
      </div>
    );
  }

  // Default Week 3 layout for the other five intents — answer in the wide
  // column, evidence in the sidebar.
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <Card className="lg:col-span-2">
        <CardHeader>
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <Badge className={`${pathMeta.tone} border`}>{pathMeta.label}</Badge>
            <Badge variant="outline">{intentLabel}</Badge>
          </div>
          <CardTitle className="text-base mt-1">Answer</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="prose prose-sm max-w-none whitespace-pre-wrap text-slate-800">
            {result.answer}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Evidence</CardTitle>
          <CardDescription>{evidenceDescription(result)}</CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <ScrollArea className="h-[500px] px-6 pb-6">
            {result.path === "rag" && <ChunkEvidence chunks={result.chunks} />}
            {result.path === "structured" && (
              <StructuredEvidence rows={result.structured_evidence} />
            )}
            {result.path === "refused" && (
              <p className="text-sm text-slate-600 mt-2">
                No evidence retrieved. The query was routed to the safety policy and refused
                without accessing patient data.
              </p>
            )}
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  );
}

function evidenceDescription(result: QueryResponse): string {
  if (result.path === "rag") {
    return `${result.chunks.length} chunks retrieved (cross-encoder reranked)`;
  }
  if (result.path === "structured") {
    return `${result.structured_evidence.length} entity rows from SQL`;
  }
  return "Refused — no patient data accessed";
}

function ChunkEvidence({ chunks }: { chunks: QueryResponse["chunks"] }) {
  return (
    <div className="space-y-4">
      {chunks.map((chunk, idx) => (
        <div key={chunk.chunk_id}>
          {idx > 0 && <Separator className="mb-4" />}
          <div className="flex justify-between items-start mb-2">
            <Badge variant="secondary">Visit {chunk.visit_date.slice(0, 10)}</Badge>
            <Badge
              variant="outline"
              className="text-xs"
              title="Cross-encoder relevance score (higher = more relevant)"
            >
              {chunk.similarity.toFixed(2)}
            </Badge>
          </div>
          <p className="text-xs text-slate-700 leading-relaxed">{chunk.chunk_text}</p>
        </div>
      ))}
    </div>
  );
}

function StructuredEvidence({ rows }: { rows: StructuredEvidenceRow[] }) {
  if (rows.length === 0) {
    return <p className="text-sm text-slate-500 mt-2">No matching entities in the structured record.</p>;
  }

  return (
    <div className="space-y-2">
      {rows.map((row, idx) => {
        const date = row.visit_date || row.last_visit || "—";
        const entityType = row.entity_type ?? "entity";
        const text = row.entity_text ?? row.normalized_text ?? "—";
        const negated = row.negated === true;

        return (
          <div
            key={`${row.visit_id ?? "row"}-${idx}`}
            className="flex justify-between items-center gap-3 px-3 py-2 bg-slate-50 border border-slate-200 rounded"
          >
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-slate-900 truncate">{text}</p>
              <p className="text-xs text-slate-500 mt-0.5">
                {entityType} · {date.slice(0, 10)}
              </p>
            </div>
            {negated && (
              <Badge variant="outline" className="text-xs bg-amber-50 text-amber-900 border-amber-200">
                negated
              </Badge>
            )}
          </div>
        );
      })}
    </div>
  );
}
