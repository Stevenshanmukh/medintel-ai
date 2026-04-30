"use client";

import { useState } from "react";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";

import { RiskFinding, RiskAlertsResponse } from "@/lib/api";


export interface RiskAlertsCardProps {
  data: RiskAlertsResponse | null;
  loading?: boolean;
  error?: string | null;
}

export function RiskAlertsCard({ data, loading, error }: RiskAlertsCardProps) {
  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Risk alerts</CardTitle>
          <CardDescription>Scanning structured visit data...</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className="border-red-200">
        <CardHeader>
          <CardTitle className="text-red-700">Risk alerts unavailable</CardTitle>
          <CardDescription className="text-red-600">{error}</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  if (!data) return null;

  const { findings, severity_counts, total_visits } = data;
  const totalCount = findings.length;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-baseline justify-between gap-3 flex-wrap">
          <div>
            <CardTitle>Risk alerts</CardTitle>
            <CardDescription>
              Rule-based detectors over {total_visits} visits.{" "}
              <span className="text-slate-400">
                Demonstration tool. Not for clinical use.
              </span>
            </CardDescription>
          </div>
          <SeverityCountsBadge counts={severity_counts} />
        </div>
      </CardHeader>
      <CardContent>
        {totalCount === 0 ? (
          <p className="text-sm text-slate-600">
            No findings. The detectors found no escalating symptoms, new
            medications, or known drug interactions in the current record.
          </p>
        ) : (
          <div className="space-y-3">
            {findings.map((f, idx) => (
              <FindingItem key={`${f.detector}-${f.title}-${idx}`} finding={f} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}


function SeverityCountsBadge({
  counts,
}: {
  counts: { high: number; moderate: number; low: number };
}) {
  const total = counts.high + counts.moderate + counts.low;
  if (total === 0) {
    return (
      <Badge variant="secondary" className="bg-emerald-100 text-emerald-800">
        clear
      </Badge>
    );
  }
  return (
    <div className="flex items-center gap-1.5">
      {counts.high > 0 && (
        <Badge className="bg-rose-100 text-rose-900 border-rose-200 border">
          {counts.high} high
        </Badge>
      )}
      {counts.moderate > 0 && (
        <Badge className="bg-amber-100 text-amber-900 border-amber-200 border">
          {counts.moderate} moderate
        </Badge>
      )}
      {counts.low > 0 && (
        <Badge className="bg-slate-100 text-slate-700 border-slate-200 border">
          {counts.low} low
        </Badge>
      )}
    </div>
  );
}


function FindingItem({ finding }: { finding: RiskFinding }) {
  const [expanded, setExpanded] = useState(false);

  const severityStyles =
    finding.severity === "high"
      ? "border-l-rose-500 bg-rose-50/40"
      : finding.severity === "moderate"
      ? "border-l-amber-500 bg-amber-50/40"
      : "border-l-slate-400 bg-slate-50/40";

  const severityBadge =
    finding.severity === "high"
      ? "bg-rose-100 text-rose-900 border-rose-200"
      : finding.severity === "moderate"
      ? "bg-amber-100 text-amber-900 border-amber-200"
      : "bg-slate-100 text-slate-700 border-slate-200";

  const detectorLabel = formatDetectorLabel(finding.detector);

  return (
    <div className={`border-l-4 rounded-r border border-slate-200 ${severityStyles} p-3`}>
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5 flex-wrap mb-1">
            <Badge className={`${severityBadge} border text-xs`}>
              {finding.severity}
            </Badge>
            <Badge variant="outline" className="text-xs">
              {detectorLabel}
            </Badge>
          </div>
          <p className="text-sm font-medium text-slate-900">{finding.title}</p>
          <p className="text-xs text-slate-700 mt-1 leading-relaxed">
            {finding.summary}
          </p>
        </div>
      </div>
      <div className="pt-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setExpanded((v) => !v)}
          className="text-xs h-7 px-2"
        >
          {expanded ? "Hide evidence" : "Show evidence"}
        </Button>
        {expanded && (
          <div className="mt-2">
            <Separator className="mb-2" />
            <pre className="text-xs bg-white border border-slate-200 rounded p-2 overflow-x-auto">
              {JSON.stringify(finding.evidence, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}


function formatDetectorLabel(detector: string): string {
  switch (detector) {
    case "symptom_escalation":
      return "symptom escalation";
    case "new_medication":
      return "new medication";
    case "drug_interaction":
      return "drug interaction";
    default:
      return detector.replace(/_/g, " ");
  }
}
