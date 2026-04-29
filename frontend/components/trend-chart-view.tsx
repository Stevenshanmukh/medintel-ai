"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Dot,
} from "recharts";

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

export interface TrendPoint {
  visit_date: string;
  status: "affirmed" | "denied" | "absent" | string;
  matched_count: number;
  matched_entities: string[];
}

export interface TrendChartViewProps {
  points: TrendPoint[];
  findingNote?: string | null;
  loading?: boolean;
  error?: string | null;
  // Optional header content. If omitted, the chart renders without a header.
  title?: string;
  description?: string;
  headerRight?: React.ReactNode;
}

export function TrendChartView({
  points,
  findingNote,
  loading,
  error,
  title,
  description,
  headerRight,
}: TrendChartViewProps) {
  const chartData = points.map((p) => ({
    date: p.visit_date,
    count: p.matched_count,
    status: p.status,
    entities: p.matched_entities.join(", ") || "—",
  }));

  return (
    <Card>
      {(title || description || headerRight) && (
        <CardHeader>
          <div className="flex items-baseline justify-between gap-3 flex-wrap">
            <div>
              {title && <CardTitle>{title}</CardTitle>}
              {description && <CardDescription>{description}</CardDescription>}
            </div>
            {headerRight}
          </div>
        </CardHeader>
      )}
      <CardContent>
        {loading && <p className="text-sm text-slate-500">Loading trend...</p>}
        {error && <p className="text-sm text-red-600">{error}</p>}
        {!loading && !error && chartData.length > 0 && (
          <div className="w-full h-56">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={chartData}
                margin={{ top: 8, right: 16, bottom: 8, left: 0 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                <YAxis
                  allowDecimals={false}
                  tick={{ fontSize: 11 }}
                  domain={[0, "dataMax + 1"]}
                />
                <Tooltip
                  contentStyle={{ fontSize: 12 }}
                  formatter={(value: any, _name: string, item: any) => {
                    const status = item?.payload?.status ?? "—";
                    const entities = item?.payload?.entities ?? "—";
                    return [`count ${value} (${status})`, entities];
                  }}
                  labelFormatter={(label) => `Visit: ${label}`}
                />
                <Line
                  type="monotone"
                  dataKey="count"
                  stroke="#3b82f6"
                  strokeWidth={2}
                  dot={(props: any) => (
                    <StatusDot {...props} status={props.payload?.status} />
                  )}
                  activeDot={{ r: 6 }}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}

        {findingNote && (
          <p className="mt-3 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded p-2">
            {findingNote}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function StatusDot(props: any) {
  const { cx, cy, status } = props;
  if (cx == null || cy == null) return null;
  const fill =
    status === "affirmed"
      ? "#16a34a"
      : status === "denied"
      ? "#dc2626"
      : "#94a3b8";
  return <Dot cx={cx} cy={cy} r={5} fill={fill} stroke="white" strokeWidth={1.5} />;
}

export function extractFindingNote(answer: string | null | undefined): string | null {
  if (!answer) return null;
  const idx = answer.indexOf("Note:");
  if (idx === -1) return null;
  return answer.slice(idx).trim();
}

export function evidenceRowsToPoints(
  rows: { visit_date: string | null; status: string | null; matched_entities: string[] | null }[]
): TrendPoint[] {
  return rows
    .filter((r) => r.visit_date && r.status)
    .map((r) => {
      const entities = r.matched_entities ?? [];
      return {
        visit_date: r.visit_date as string,
        status: r.status as string,
        matched_count: entities.length,
        matched_entities: entities,
      };
    });
}
