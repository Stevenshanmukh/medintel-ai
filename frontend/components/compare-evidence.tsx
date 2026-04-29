"use client";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { StructuredEvidenceRow } from "@/lib/api";

export interface CompareEvidenceProps {
  rows: StructuredEvidenceRow[];
  // Optional answer text from the response, used to extract the visit labels
  // and any subject filter mention for the header. If absent, we fall back to
  // the visit dates pulled from the rows.
  answer?: string | null;
}

interface DiffSection {
  label: string;
  status: "added" | "removed" | "new" | "resolved";
  category: "medication" | "symptom";
  rows: StructuredEvidenceRow[];
  colorClass: string;
}

export function CompareEvidence({ rows, answer }: CompareEvidenceProps) {
  // Pull dates from any row (all rows have the same visit_a/visit_b in a single
  // compare query).
  const sample = rows[0];
  const visitA = sample?.visit_a ?? null;
  const visitB = sample?.visit_b ?? null;

  // Detect "no diff" early — empty rows means the two visits had identical
  // entity sets under the current filter, OR the subject filter excluded
  // everything. The answer text usually clarifies which.
  if (rows.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Visit comparison</CardTitle>
          {visitA && visitB && (
            <CardDescription>
              Comparing {visitA} to {visitB}
            </CardDescription>
          )}
        </CardHeader>
        <CardContent>
          <p className="text-sm text-slate-600">
            No differences found. The two visits had matching entities under
            the current filter (or the subject didn't match anything in
            either visit).
          </p>
        </CardContent>
      </Card>
    );
  }

  // Build the four sections. Empty sections are dropped from the render.
  const sections: DiffSection[] = [
    {
      label: `Medications added in ${visitB}`,
      status: "added",
      category: "medication",
      rows: rows.filter(
        (r) => r.category === "medication" && r.diff_status === "added"
      ),
      colorClass: "bg-emerald-100 text-emerald-800",
    },
    {
      label: `Medications removed by ${visitB}`,
      status: "removed",
      category: "medication",
      rows: rows.filter(
        (r) => r.category === "medication" && r.diff_status === "removed"
      ),
      colorClass: "bg-rose-100 text-rose-800",
    },
    {
      label: `New symptoms in ${visitB}`,
      status: "new",
      category: "symptom",
      rows: rows.filter(
        (r) => r.category === "symptom" && r.diff_status === "new"
      ),
      colorClass: "bg-amber-100 text-amber-800",
    },
    {
      label: `Symptoms resolved by ${visitB}`,
      status: "resolved",
      category: "symptom",
      rows: rows.filter(
        (r) => r.category === "symptom" && r.diff_status === "resolved"
      ),
      colorClass: "bg-sky-100 text-sky-800",
    },
  ];

  const populatedSections = sections.filter((s) => s.rows.length > 0);

  // Pull a subject mention from the answer text if present (the handler emits
  // "Comparing 'chest pain'-related changes between..." when filtered).
  const subjectMatch = answer?.match(/Comparing '([^']+)'-related changes/);
  const subject = subjectMatch?.[1] ?? null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Visit comparison</CardTitle>
        <CardDescription>
          {subject ? (
            <>
              <span className="font-medium">'{subject}'</span>-related changes
              between {visitA} and {visitB}
            </>
          ) : (
            <>
              Comparing {visitA} to {visitB}
            </>
          )}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {populatedSections.map((section) => (
            <DiffSectionPanel key={`${section.category}-${section.status}`} section={section} />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function DiffSectionPanel({ section }: { section: DiffSection }) {
  const arrow =
    section.status === "added" || section.status === "new"
      ? "→"
      : section.status === "removed" || section.status === "resolved"
      ? "←"
      : "·";

  return (
    <div className="border rounded-md p-3 bg-slate-50/50">
      <div className="text-xs font-medium text-slate-600 mb-2 flex items-center gap-1.5">
        <span className="text-slate-400">{arrow}</span>
        {section.label}
        <span className="text-slate-400 font-normal">({section.rows.length})</span>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {section.rows.map((r) => (
          <Badge
            key={`${r.category}-${r.diff_status}-${r.name}`}
            variant="secondary"
            className={section.colorClass}
          >
            {r.name}
          </Badge>
        ))}
      </div>
    </div>
  );
}
