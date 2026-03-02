/**
 * LossCurveChart — Real-time loss curve visualization using recharts
 */

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
import type { TrainingMetrics, TrainingRun } from "../../types/ruh";

interface LossCurveChartProps {
  metrics: TrainingMetrics;
  history?: TrainingRun[];
}

const STAGE_COLORS: Record<string, string> = {
  nutfah: "#8b5cf6",
  alaqah: "#3b82f6",
  mudghah: "#10b981",
  khalq_akhar: "#f59e0b",
};

export function LossCurveChart({ metrics, history = [] }: LossCurveChartProps) {
  // Build data points from current run losses
  const currentData = metrics.losses.map((loss, idx) => ({
    epoch: idx + 1,
    current: loss,
  }));

  // Merge historical runs as additional series
  const historicalSeries: { key: string; color: string; data: { epoch: number; loss: number }[] }[] = [];
  history.slice(-3).forEach((run, idx) => {
    if (run.losses.length > 0) {
      const key = `${run.stage}_${idx}`;
      historicalSeries.push({
        key,
        color: STAGE_COLORS[run.stage] ?? "#94a3b8",
        data: run.losses.map((loss, epoch) => ({ epoch: epoch + 1, loss })),
      });
    }
  });

  // Combine data for charting
  const maxEpochs = Math.max(
    currentData.length,
    ...historicalSeries.map((s) => s.data.length),
    1,
  );

  const chartData = Array.from({ length: maxEpochs }, (_, i) => {
    const point: Record<string, unknown> = { epoch: i + 1 };
    if (i < currentData.length) {
      point.current = currentData[i].current;
    }
    historicalSeries.forEach((series) => {
      if (i < series.data.length) {
        point[series.key] = series.data[i].loss;
      }
    });
    return point;
  });

  const noData = currentData.length === 0 && historicalSeries.length === 0;

  return (
    <div className="space-y-2">
      <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
        Loss Curve
      </h4>
      {noData ? (
        <div className="flex items-center justify-center h-48 bg-gray-50 dark:bg-zinc-800/30 rounded-lg border border-dashed border-gray-200 dark:border-zinc-700">
          <p className="text-sm text-gray-400">No training data yet</p>
        </div>
      ) : (
        <div className="h-64 bg-gray-50 dark:bg-zinc-800/30 rounded-lg border border-gray-100 dark:border-zinc-700/50 p-2">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
              <XAxis
                dataKey="epoch"
                tick={{ fontSize: 11, fill: "#9ca3af" }}
                label={{ value: "Epoch", position: "bottom", fontSize: 11, fill: "#9ca3af" }}
              />
              <YAxis
                tick={{ fontSize: 11, fill: "#9ca3af" }}
                label={{ value: "Loss", angle: -90, position: "insideLeft", fontSize: 11, fill: "#9ca3af" }}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#1f2937",
                  border: "1px solid #374151",
                  borderRadius: "8px",
                  fontSize: 12,
                  color: "#e5e7eb",
                }}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              {currentData.length > 0 && (
                <Line
                  type="monotone"
                  dataKey="current"
                  stroke="#a855f7"
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  name={`Current (${metrics.stage ?? "training"})`}
                  animationDuration={300}
                />
              )}
              {historicalSeries.map((series) => (
                <Line
                  key={series.key}
                  type="monotone"
                  dataKey={series.key}
                  stroke={series.color}
                  strokeWidth={1}
                  strokeDasharray="5 5"
                  dot={false}
                  name={series.key}
                  animationDuration={300}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
