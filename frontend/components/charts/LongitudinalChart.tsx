"use client";

import React from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import { format, parseISO } from "date-fns";
import type { LongitudinalPoint } from "@/types";

interface LongitudinalChartProps {
  data:      LongitudinalPoint[];
  metric:    "et_volume_ml" | "bidimensional_product_mm2";
  title:     string;
  unit:      string;
  nadirDate: string;
}

function CustomDot(props: {
  cx?: number;
  cy?: number;
  payload?: LongitudinalPoint;
}) {
  const { cx = 0, cy = 0, payload } = props;
  if (payload?.is_nadir) {
    return (
      <g>
        <circle cx={cx} cy={cy} r={7} fill="var(--amber)" stroke="var(--surface)" strokeWidth={2} />
        <text x={cx} y={cy - 14} textAnchor="middle" fill="var(--amber)" fontSize={9} fontWeight="bold" fontFamily="monospace">
          NADIR
        </text>
      </g>
    );
  }
  return <circle cx={cx} cy={cy} r={4} fill="var(--blue)" stroke="var(--surface)" strokeWidth={2} />;
}

function CustomTooltip({
  active,
  payload,
  unit,
}: {
  active?:  boolean;
  payload?: Array<{ value: number; payload: LongitudinalPoint }>;
  unit:     string;
}) {
  if (!active || !payload?.length) return null;
  const pt  = payload[0].payload;
  const val = payload[0].value;
  return (
    <div
      className="rounded-lg px-3 py-2.5 shadow-xl text-[11px]"
      style={{ border: "1px solid var(--border)", backgroundColor: "var(--surface)" }}
    >
      <p className="font-semibold mb-1" style={{ color: "var(--text)" }}>
        {format(parseISO(pt.scan_date), "dd MMM yyyy")}
      </p>
      <p className="font-mono font-bold" style={{ color: "var(--blue)" }}>
        {val.toFixed(2)} {unit}
      </p>
      {pt.rano_class && (
        <p className="mt-1" style={{ color: "var(--muted)" }}>{pt.rano_class}</p>
      )}
      {pt.is_nadir && (
        <p className="font-semibold mt-1" style={{ color: "var(--amber)" }}>⬟ Nadir (best response)</p>
      )}
      {pt.change_from_nadir_pct !== null && (
        <p
          className="font-mono mt-0.5"
          style={{
            color:
              (pt.change_from_nadir_pct ?? 0) > 0 ? "var(--red)" :
              (pt.change_from_nadir_pct ?? 0) < 0 ? "var(--green)" :
              "var(--muted)",
          }}
        >
          {(pt.change_from_nadir_pct ?? 0) > 0 ? "+" : ""}
          {(pt.change_from_nadir_pct ?? 0).toFixed(1)}% from nadir
        </p>
      )}
    </div>
  );
}

export default function LongitudinalChart({
  data,
  metric,
  title,
  unit,
  nadirDate,
}: LongitudinalChartProps) {
  if (!data || data.length < 2) {
    return (
      <div
        className="flex items-center justify-center rounded-xl border h-[220px] text-[12px]"
        style={{ borderColor: "var(--border)", backgroundColor: "var(--surface)", color: "var(--muted)" }}
      >
        At least 2 timepoints required for chart
      </div>
    );
  }

  const chartData = data.map((pt) => ({
    ...pt,
    date:  format(parseISO(pt.scan_date), "MMM yy"),
    value: pt[metric],
  }));

  const allValues = chartData.map((d) => d.value);
  const minVal    = Math.min(...allValues);
  const maxVal    = Math.max(...allValues);
  const padding   = (maxVal - minVal) * 0.15 || 1;
  const yMin      = Math.max(0, minVal - padding);
  const yMax      = maxVal + padding;

  return (
    <div
      className="rounded-xl border p-5"
      style={{ borderColor: "var(--border)", backgroundColor: "var(--surface)" }}
    >
      <div className="flex items-center justify-between mb-4">
        <p className="text-[12px] font-semibold" style={{ color: "var(--text)" }}>{title}</p>
        <span className="text-[10px] font-mono" style={{ color: "var(--muted)" }}>{unit}</span>
      </div>

      <div style={{ width: "100%", height: 220 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 16, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
            <XAxis
              dataKey="date"
              tick={{ fill: "var(--muted)", fontSize: 10, fontFamily: "monospace" }}
              axisLine={{ stroke: "var(--border)" }}
              tickLine={false}
            />
            <YAxis
              domain={[yMin, yMax]}
              tick={{ fill: "var(--muted)", fontSize: 10, fontFamily: "monospace" }}
              axisLine={false}
              tickLine={false}
              width={48}
              tickFormatter={(v) => v.toFixed(1)}
            />
            <Tooltip content={<CustomTooltip unit={unit} />} />
            {nadirDate && (
              <ReferenceLine
                x={format(parseISO(nadirDate), "MMM yy")}
                stroke="var(--amber)"
                strokeDasharray="4 2"
                strokeWidth={1.5}
                label={{ value: "Nadir", position: "top", fill: "var(--amber)", fontSize: 9, fontFamily: "monospace" }}
              />
            )}
            <Line
              type="monotone"
              dataKey="value"
              stroke="var(--blue)"
              strokeWidth={2}
              dot={<CustomDot />}
              activeDot={{ r: 5, fill: "var(--blue)", stroke: "var(--surface)", strokeWidth: 2 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}