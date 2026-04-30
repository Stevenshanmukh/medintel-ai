"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

import {
  getPatientVisits,
  getPatientRiskAlerts,
  PatientVisitsResponse,
  RiskAlertsResponse,
  VisitTimelineEntry,
} from "@/lib/api";

import { RiskAlertsCard } from "@/components/risk-alerts-card";


export default function PatientDashboardPage() {
  const params = useParams<{ id: string }>();
  const patientId = params.id;

  const [visits, setVisits] = useState<PatientVisitsResponse | null>(null);
  const [visitsLoading, setVisitsLoading] = useState(true);
  const [visitsError, setVisitsError] = useState<string | null>(null);

  const [alerts, setAlerts] = useState<RiskAlertsResponse | null>(null);
  const [alertsLoading, setAlertsLoading] = useState(true);
  const [alertsError, setAlertsError] = useState<string | null>(null);

  useEffect(() => {
    if (!patientId) return;
    setVisitsLoading(true);
    getPatientVisits(patientId)
      .then((res) => {
        setVisits(res);
        setVisitsError(null);
      })
      .catch((e) =>
        setVisitsError(e instanceof Error ? e.message : String(e))
      )
      .finally(() => setVisitsLoading(false));
  }, [patientId]);

  useEffect(() => {
    if (!patientId) return;
    setAlertsLoading(true);
    getPatientRiskAlerts(patientId)
      .then((res) => {
        setAlerts(res);
        setAlertsError(null);
      })
      .catch((e) =>
        setAlertsError(e instanceof Error ? e.message : String(e))
      )
      .finally(() => setAlertsLoading(false));
  }, [patientId]);

  const latestVisit = useMemo<VisitTimelineEntry | null>(() => {
    if (!visits || visits.visits.length === 0) return null;
    return visits.visits[visits.visits.length - 1];
  }, [visits]);

  if (visitsLoading) {
    return (
      <div className="max-w-5xl mx-auto p-8">
        <p className="text-slate-500">Loading patient...</p>
      </div>
    );
  }

  if (visitsError) {
    return (
      <div className="max-w-5xl mx-auto p-8">
        <Card className="border-red-200">
          <CardHeader>
            <CardTitle className="text-red-700">Failed to load patient</CardTitle>
            <CardDescription className="text-red-600">{visitsError}</CardDescription>
          </CardHeader>
        </Card>
      </div>
    );
  }

  if (!visits) return null;

  const visitCount = visits.visits.length;
  const latestVisitDate = latestVisit?.visit_date ?? "—";

  return (
    <div className="max-w-5xl mx-auto p-8 space-y-6">
      {/* Section: Patient header */}
      <header>
        <div className="flex items-baseline justify-between gap-3 flex-wrap">
          <div>
            <h1 className="text-3xl font-semibold">{visits.patient.name}</h1>
            <p className="text-slate-500 mt-1">
              MRN {visits.patient.mrn ?? "—"} · {visitCount} visit
              {visitCount !== 1 ? "s" : ""} on file · last visit {latestVisitDate}
            </p>
          </div>
          <div className="flex gap-2">
            <Button asChild variant="outline">
              <Link href={`/patients/${patientId}/timeline`}>
                Full timeline
              </Link>
            </Button>
            <Button asChild>
              <Link href="/query">Ask a question</Link>
            </Button>
          </div>
        </div>
      </header>

      <Separator />

      {/* Section: Risk alerts */}
      <RiskAlertsCard
        data={alerts}
        loading={alertsLoading}
        error={alertsError}
        compact
      />

      {/* Section: Current medications + Active concerns side by side */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Current medications</CardTitle>
            <CardDescription>
              {latestVisit
                ? `${latestVisit.entities.medications_affirmed.length} medication${
                    latestVisit.entities.medications_affirmed.length !== 1 ? "s" : ""
                  } at ${latestVisitDate}`
                : "—"}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <BadgeGroup
              items={latestVisit?.entities.medications_affirmed ?? []}
              colorClass="bg-blue-100 text-blue-800 hover:bg-blue-200"
              emptyMessage="No medications recorded at the latest visit."
            />
            <p className="text-xs text-slate-400 mt-3">
              Reflects the most recent visit's record. For a cross-visit query
              (e.g. medications discontinued earlier), use the question
              interface.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Active concerns</CardTitle>
            <CardDescription>
              {latestVisit
                ? `${latestVisit.entities.symptoms_affirmed.length} affirmed at ${latestVisitDate}`
                : "—"}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <BadgeGroup
              items={latestVisit?.entities.symptoms_affirmed ?? []}
              colorClass="bg-amber-100 text-amber-800 hover:bg-amber-200"
              emptyMessage="No active symptoms at the latest visit."
            />
            {latestVisit && latestVisit.entities.symptoms_denied.length > 0 && (
              <div className="mt-4 pt-3 border-t border-slate-100">
                <p className="text-xs font-medium text-slate-500 mb-1.5">
                  Explicitly denied at latest visit
                </p>
                <BadgeGroup
                  items={latestVisit.entities.symptoms_denied}
                  colorClass="bg-slate-100 text-slate-600 line-through hover:bg-slate-200"
                  emptyMessage=""
                />
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Section: Recent activity */}
      <Card>
        <CardHeader>
          <CardTitle>Recent activity</CardTitle>
          <CardDescription>
            {visits.visits.length > 0
              ? `Last ${Math.min(3, visits.visits.length)} of ${visits.visits.length} visits`
              : "No visits"}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <RecentActivityList
            visits={visits.visits}
            patientId={patientId}
          />
        </CardContent>
      </Card>
    </div>
  );
}

function BadgeGroup({
  items,
  colorClass,
  emptyMessage,
}: {
  items: string[];
  colorClass: string;
  emptyMessage: string;
}) {
  if (items.length === 0) {
    return emptyMessage ? (
      <p className="text-sm text-slate-500">{emptyMessage}</p>
    ) : null;
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((item) => (
        <Badge key={item} variant="secondary" className={colorClass}>
          {item}
        </Badge>
      ))}
    </div>
  );
}

function RecentActivityList({
  visits,
  patientId,
}: {
  visits: VisitTimelineEntry[];
  patientId: string;
}) {
  // visits arrive in chronological ASC order from the API. Reverse and take 3
  // for "most recent first."
  const recent = [...visits].reverse().slice(0, 3);

  if (recent.length === 0) {
    return <p className="text-sm text-slate-500">No visits on file.</p>;
  }

  return (
    <ul className="space-y-2">
      {recent.map((visit) => {
        const totalEntities =
          visit.entities.medications_affirmed.length +
          visit.entities.symptoms_affirmed.length +
          visit.entities.symptoms_denied.length;
        return (
          <li key={visit.visit_id}>
            <Link
              href={`/patients/${patientId}/timeline#visit-${visit.visit_number}`}
              className="block px-3 py-2.5 rounded border border-slate-200 hover:border-slate-300 hover:bg-slate-50 transition"
            >
              <div className="flex items-baseline justify-between gap-3 flex-wrap">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-slate-900">
                    Visit {visit.visit_number} · {visit.visit_date}
                  </p>
                  {visit.chief_complaint && (
                    <p className="text-xs text-slate-600 mt-0.5 truncate">
                      {visit.chief_complaint}
                    </p>
                  )}
                </div>
                <span className="text-xs text-slate-400 flex-shrink-0">
                  {totalEntities} entit{totalEntities !== 1 ? "ies" : "y"}
                </span>
              </div>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
