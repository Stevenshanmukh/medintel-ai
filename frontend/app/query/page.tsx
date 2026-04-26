"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { listPatients, runQuery, type Patient, type QueryResponse } from "@/lib/api";

export default function QueryPage() {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [selectedPatient, setSelectedPatient] = useState<string | null>(null);
  const [question, setQuestion] = useState("How have Sarah Chen's symptoms progressed over time?");
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
            Ask grounded questions about a patient's record. All answers are derived from stored visit
            transcripts.
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

        {result && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <Card className="lg:col-span-2">
              <CardHeader>
                <CardTitle className="text-base">Answer</CardTitle>
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
                <CardDescription>{result.chunks.length} chunks retrieved</CardDescription>
              </CardHeader>
              <CardContent className="p-0">
                <ScrollArea className="h-[500px] px-6 pb-6">
                  <div className="space-y-4">
                    {result.chunks.map((chunk, idx) => (
                      <div key={chunk.chunk_id}>
                        {idx > 0 && <Separator className="mb-4" />}
                        <div className="flex justify-between items-start mb-2">
                          <Badge variant="secondary">Visit {chunk.visit_date.slice(0, 10)}</Badge>
                          <Badge variant="outline" className="text-xs">
                            {(chunk.similarity * 100).toFixed(1)}%
                          </Badge>
                        </div>
                        <p className="text-xs text-slate-700 leading-relaxed">{chunk.chunk_text}</p>
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </main>
  );
}
