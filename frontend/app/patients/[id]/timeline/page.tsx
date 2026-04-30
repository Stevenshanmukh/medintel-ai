"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import {
  getPatientVisits,
  getPatientRiskAlerts,
  getTrendableSubjects,
  runQuery,
  PatientVisitsResponse,
  RiskAlertsResponse,
  VisitTimelineEntry,
  StructuredEvidenceRow,
  TrendableSubjects,
} from "@/lib/api";

import {
  TrendChartView,
  TrendPoint,
  extractFindingNote,
  evidenceRowsToPoints,
} from "@/components/trend-chart-view";

import { RiskAlertsCard } from "@/components/risk-alerts-card";


export default function TimelinePage() {
  const params = useParams<{ id: string }>();
  const patientId = params.id;

  const [data, setData] = useState<PatientVisitsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [riskAlerts, setRiskAlerts] = useState<RiskAlertsResponse | null>(null);
  const [riskLoading, setRiskLoading] = useState(true);
  const [riskError, setRiskError] = useState<string | null>(null);

  useEffect(() => {
    if (!patientId) return;
    setLoading(true);
    getPatientVisits(patientId)
      .then((res) => {
        setData(res);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [patientId]);

  useEffect(() => {
    if (!patientId) return;
    setRiskLoading(true);
    getPatientRiskAlerts(patientId)
      .then((res) => {
        setRiskAlerts(res);
        setRiskError(null);
      })
      .catch((e) => setRiskError(e instanceof Error ? e.message : String(e)))
      .finally(() => setRiskLoading(false));
  }, [patientId]);

  const trendableSubjects = useMemo<TrendableSubjects>(() => {
    if (!data) return { symptoms: [], medications: [] };
    return getTrendableSubjects(data.visits);
  }, [data]);

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto p-8">
        <p className="text-slate-500">Loading patient timeline...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-4xl mx-auto p-8">
        <Card className="border-red-200">
          <CardHeader>
            <CardTitle className="text-red-700">
              Failed to load timeline
            </CardTitle>
            <CardDescription className="text-red-600">{error}</CardDescription>
          </CardHeader>
        </Card>
      </div>
    );
  }

  if (!data) {
    return null;
  }

  return (
    <div className="max-w-4xl mx-auto p-8 space-y-6">
      <header>
        <h1 className="text-3xl font-semibold">{data.patient.name}</h1>
        <p className="text-slate-500">
          MRN {data.patient.mrn ?? "—"} · {data.visits.length} visit
          {data.visits.length !== 1 ? "s" : ""}
        </p>
      </header>

      <Separator />

      <RiskAlertsCard
        data={riskAlerts}
        loading={riskLoading}
        error={riskError}
      />

      <Separator />

      <TrendChart
        patientId={patientId}
        subjects={trendableSubjects}
      />

      <Separator />

      <div className="relative space-y-6">
        <div
          className="absolute left-4 top-2 bottom-2 w-px bg-slate-200"
          aria-hidden="true"
        />
        {data.visits.map((visit) => (
          <VisitCard key={visit.visit_id} visit={visit} />
        ))}
      </div>
    </div>
  );
}


// ---------- Trend Chart ----------

interface TrendChartProps {
  patientId: string;
  subjects: TrendableSubjects;
}

function TrendChart({ patientId, subjects }: TrendChartProps) {
  const defaultSubject =
    subjects.symptoms[0] ?? subjects.medications[0] ?? null;

  const [subject, setSubject] = useState<string | null>(defaultSubject);
  const [trendAnswer, setTrendAnswer] = useState<string | null>(null);
  const [trendPoints, setTrendPoints] = useState<TrendPoint[]>([]);
  const [trendLoading, setTrendLoading] = useState(false);
  const [trendError, setTrendError] = useState<string | null>(null);

  // Fire a trend query whenever the subject changes
  useEffect(() => {
    if (!subject) return;
    setTrendLoading(true);
    setTrendError(null);
    runQuery(`How has her ${subject} trended?`, patientId, 5, "strict")
      .then((res) => {
        if (res.intent !== "trend_over_time") {
          setTrendError(
            `Expected trend_over_time, got "${res.intent}". The classifier ` +
              `routed this query to a different path.`
          );
          setTrendAnswer(res.answer);
          setTrendPoints([]);
          return;
        }
        setTrendAnswer(res.answer);
        setTrendPoints(evidenceRowsToPoints(res.structured_evidence));
      })
      .catch((e) =>
        setTrendError(e instanceof Error ? e.message : String(e))
      )
      .finally(() => setTrendLoading(false));
  }, [subject, patientId]);

  if (!defaultSubject) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Trend</CardTitle>
          <CardDescription>
            No trendable subjects found (need 2+ mentions across visits).
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  const subjectPicker = (
    <Select
      value={subject ?? undefined}
      onValueChange={(v) => setSubject(v)}
    >
      <SelectTrigger className="w-[220px]">
        <SelectValue placeholder="Choose subject" />
      </SelectTrigger>
      <SelectContent>
        {subjects.symptoms.length > 0 && (
          <SelectGroup>
            <SelectLabel>Symptoms</SelectLabel>
            {subjects.symptoms.map((s) => (
              <SelectItem key={`s-${s}`} value={s}>
                {s}
              </SelectItem>
            ))}
          </SelectGroup>
        )}
        {subjects.medications.length > 0 && (
          <SelectGroup>
            <SelectLabel>Medications</SelectLabel>
            {subjects.medications.map((m) => (
              <SelectItem key={`m-${m}`} value={m}>
                {m}
              </SelectItem>
            ))}
          </SelectGroup>
        )}
      </SelectContent>
    </Select>
  );

  return (
    <TrendChartView
      points={trendPoints}
      findingNote={extractFindingNote(trendAnswer)}
      loading={trendLoading}
      error={trendError}
      title="Trend over time"
      description="Mentions per visit, color-coded by status"
      headerRight={subjectPicker}
    />
  );
}





// ---------- Visit card (unchanged) ----------

function VisitCard({ visit }: { visit: VisitTimelineEntry }) {
  const [expanded, setExpanded] = useState(false);

  const meds = visit.entities.medications_affirmed;
  const affirmedSymptoms = visit.entities.symptoms_affirmed;
  const deniedSymptoms = visit.entities.symptoms_denied;

  return (
    <div className="relative pl-12">
      <div className="absolute left-2 top-4 w-5 h-5 rounded-full bg-blue-500 border-4 border-white shadow" />

      <Card>
        <CardHeader>
          <div className="flex items-baseline justify-between gap-3 flex-wrap">
            <CardTitle className="text-lg">
              Visit {visit.visit_number} · {visit.visit_date}
            </CardTitle>
            <span className="text-xs text-slate-500">
              {meds.length + affirmedSymptoms.length + deniedSymptoms.length}{" "}
              entities
            </span>
          </div>
          {visit.chief_complaint && (
            <CardDescription>{visit.chief_complaint}</CardDescription>
          )}
        </CardHeader>

        <CardContent className="space-y-3">
          {meds.length > 0 && (
            <EntitySection
              label="Medications"
              items={meds}
              colorClass="bg-blue-100 text-blue-800 hover:bg-blue-200"
            />
          )}
          {affirmedSymptoms.length > 0 && (
            <EntitySection
              label="Symptoms (affirmed)"
              items={affirmedSymptoms}
              colorClass="bg-amber-100 text-amber-800 hover:bg-amber-200"
            />
          )}
          {deniedSymptoms.length > 0 && (
            <EntitySection
              label="Symptoms (denied)"
              items={deniedSymptoms}
              colorClass="bg-slate-100 text-slate-600 line-through hover:bg-slate-200"
            />
          )}

          <div className="pt-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setExpanded((v) => !v)}
            >
              {expanded ? "Hide transcript" : "Show transcript"}
            </Button>
            {expanded && (
              <pre className="mt-2 p-3 bg-slate-50 border rounded text-xs whitespace-pre-wrap font-mono leading-relaxed">
                {visit.raw_transcript}
              </pre>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}


function EntitySection({
  label,
  items,
  colorClass,
}: {
  label: string;
  items: string[];
  colorClass: string;
}) {
  return (
    <div>
      <div className="text-xs font-medium text-slate-500 mb-1">{label}</div>
      <div className="flex flex-wrap gap-1.5">
        {items.map((item) => (
          <Badge key={item} variant="secondary" className={colorClass}>
            {item}
          </Badge>
        ))}
      </div>
    </div>
  );
}
