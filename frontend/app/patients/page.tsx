"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

import { listPatients, type Patient } from "@/lib/api";


export default function PatientsListPage() {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    listPatients()
      .then((res) => {
        setPatients(res);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="max-w-5xl mx-auto p-8 space-y-6">
      <header>
        <h1 className="text-3xl font-semibold">Patients</h1>
        <p className="text-slate-500 mt-1">
          {loading
            ? "Loading..."
            : `${patients.length} patient${patients.length !== 1 ? "s" : ""} on file`}
        </p>
      </header>

      <Separator />

      {error && (
        <Card className="border-red-200">
          <CardHeader>
            <CardTitle className="text-red-700">Failed to load patients</CardTitle>
            <CardDescription className="text-red-600">{error}</CardDescription>
          </CardHeader>
        </Card>
      )}

      {!loading && !error && patients.length === 0 && (
        <Card>
          <CardContent className="py-8">
            <p className="text-slate-500 text-center">
              No patients found in the database.
            </p>
          </CardContent>
        </Card>
      )}

      {!loading && !error && patients.length > 0 && (
        <ul className="space-y-2">
          {patients.map((p) => (
            <li key={p.id}>
              <Link
                href={`/patients/${p.id}`}
                className="block p-4 rounded border border-slate-200 hover:border-slate-300 hover:bg-slate-50 transition"
              >
                <div className="flex items-baseline justify-between gap-3 flex-wrap">
                  <div>
                    <p className="text-base font-medium text-slate-900">
                      {p.name}
                    </p>
                    <p className="text-xs text-slate-500 mt-0.5">
                      MRN {p.mrn ?? "—"}
                    </p>
                  </div>
                  <span className="text-xs text-slate-500">
                    {p.visit_count} visit{p.visit_count !== 1 ? "s" : ""}
                  </span>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
