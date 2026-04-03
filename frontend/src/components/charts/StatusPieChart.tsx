import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from "recharts";

export interface StatusPieChartProps {
  data: { name: string; value: number; color: string }[];
  height?: number;
  innerRadius?: number;
  outerRadius?: number;
  showLegend?: boolean;
}

export default function StatusPieChart({
  data,
  height = 300,
  innerRadius = 0,
  outerRadius = 100,
  showLegend = true,
}: StatusPieChartProps) {
  const filtered = data.filter((d) => d.value > 0);

  if (filtered.length === 0) {
    return (
      <div className="flex items-center justify-center text-sm text-gray-400" style={{ height }}>
        Sin datos disponibles
      </div>
    );
  }

  const total = filtered.reduce((sum, d) => sum + d.value, 0);

  return (
    <ResponsiveContainer width="100%" height={height}>
      <PieChart>
        <Pie
          data={filtered}
          cx="50%"
          cy="50%"
          innerRadius={innerRadius}
          outerRadius={outerRadius}
          paddingAngle={2}
          dataKey="value"
          nameKey="name"
          label={({ name, value }) => `${name}: ${value}`}
          labelLine={{ stroke: "#9ca3af", strokeWidth: 1 }}
        >
          {filtered.map((entry, index) => (
            <Cell key={index} fill={entry.color} />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{
            backgroundColor: "#fff",
            border: "1px solid #e5e7eb",
            borderRadius: "8px",
            fontSize: "12px",
          }}
          formatter={(value: number, name: string) => [
            `${value} (${((value / total) * 100).toFixed(1)}%)`,
            name,
          ]}
        />
        {showLegend && (
          <Legend
            wrapperStyle={{ fontSize: "12px" }}
            formatter={(value: string) => <span className="text-gray-600">{value}</span>}
          />
        )}
      </PieChart>
    </ResponsiveContainer>
  );
}
