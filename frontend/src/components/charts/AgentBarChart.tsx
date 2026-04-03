import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";

export interface AgentBarChartProps {
  data: { name: string; value: number; color?: string }[];
  height?: number;
  color?: string;
  layout?: "horizontal" | "vertical";
  barSize?: number;
  valueFormatter?: (value: number) => string;
}

export default function AgentBarChart({
  data,
  height = 300,
  color = "#3b82f6",
  layout = "horizontal",
  barSize = 24,
  valueFormatter,
}: AgentBarChartProps) {
  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center text-sm text-gray-400" style={{ height }}>
        Sin datos disponibles
      </div>
    );
  }

  if (layout === "vertical") {
    return (
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} layout="vertical" margin={{ top: 5, right: 20, left: 80, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" horizontal={false} />
          <XAxis type="number" tick={{ fontSize: 12, fill: "#9ca3af" }} tickFormatter={valueFormatter} />
          <YAxis
            dataKey="name"
            type="category"
            tick={{ fontSize: 12, fill: "#6b7280" }}
            width={75}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#fff",
              border: "1px solid #e5e7eb",
              borderRadius: "8px",
              fontSize: "12px",
            }}
            formatter={(value: number) => [valueFormatter ? valueFormatter(value) : value, "Valor"]}
          />
          <Bar dataKey="value" barSize={barSize} radius={[0, 4, 4, 0]}>
            {data.map((entry, index) => (
              <Cell key={index} fill={entry.color ?? color} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
        <XAxis
          dataKey="name"
          tick={{ fontSize: 11, fill: "#6b7280" }}
          interval={0}
          angle={-30}
          textAnchor="end"
          height={60}
        />
        <YAxis tick={{ fontSize: 12, fill: "#9ca3af" }} tickFormatter={valueFormatter} />
        <Tooltip
          contentStyle={{
            backgroundColor: "#fff",
            border: "1px solid #e5e7eb",
            borderRadius: "8px",
            fontSize: "12px",
          }}
          formatter={(value: number) => [valueFormatter ? valueFormatter(value) : value, "Valor"]}
        />
        <Bar dataKey="value" barSize={barSize} radius={[4, 4, 0, 0]}>
          {data.map((entry, index) => (
            <Cell key={index} fill={entry.color ?? color} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
