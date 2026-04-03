import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";

export interface TrendLineChartProps {
  data: Record<string, unknown>[];
  xKey: string;
  lines: { dataKey: string; name: string; color: string }[];
  height?: number;
  yDomain?: [number | string, number | string];
  yTickFormatter?: (value: number) => string;
  xTickFormatter?: (value: string) => string;
}

const CHART_COLORS = {
  blue: "#3b82f6",
  green: "#10b981",
  amber: "#f59e0b",
  red: "#ef4444",
  purple: "#8b5cf6",
  cyan: "#06b6d4",
};

export { CHART_COLORS };

export default function TrendLineChart({
  data,
  xKey,
  lines,
  height = 300,
  yDomain,
  yTickFormatter,
  xTickFormatter,
}: TrendLineChartProps) {
  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center text-sm text-gray-400" style={{ height }}>
        Sin datos disponibles
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis
          dataKey={xKey}
          tick={{ fontSize: 12, fill: "#9ca3af" }}
          tickFormatter={xTickFormatter}
        />
        <YAxis
          tick={{ fontSize: 12, fill: "#9ca3af" }}
          domain={yDomain}
          tickFormatter={yTickFormatter}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: "#fff",
            border: "1px solid #e5e7eb",
            borderRadius: "8px",
            fontSize: "12px",
          }}
        />
        {lines.length > 1 && <Legend wrapperStyle={{ fontSize: "12px" }} />}
        {lines.map((line) => (
          <Line
            key={line.dataKey}
            type="monotone"
            dataKey={line.dataKey}
            name={line.name}
            stroke={line.color}
            strokeWidth={2}
            dot={{ r: 3, fill: line.color }}
            activeDot={{ r: 5 }}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
