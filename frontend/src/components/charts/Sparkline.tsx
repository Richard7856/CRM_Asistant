import { LineChart, Line, ResponsiveContainer } from "recharts";

export interface SparklineProps {
  data: { value: number }[];
  color?: string;
  height?: number;
  width?: number;
}

export default function Sparkline({
  data,
  color = "#3b82f6",
  height = 32,
  width = 80,
}: SparklineProps) {
  if (!data || data.length < 2) {
    return <div style={{ width, height }} />;
  }

  return (
    <ResponsiveContainer width={width} height={height}>
      <LineChart data={data}>
        <Line
          type="monotone"
          dataKey="value"
          stroke={color}
          strokeWidth={1.5}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
