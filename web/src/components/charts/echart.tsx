import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { BarChart, LineChart, PieChart } from "echarts/charts";
import {
  DatasetComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TitleComponent,
  TooltipComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { cn } from "@/lib/utils";

echarts.use([
  BarChart,
  LineChart,
  PieChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  TitleComponent,
  MarkLineComponent,
  DatasetComponent,
  CanvasRenderer,
]);

type EChartsInstance = ReturnType<typeof echarts.init>;
export type ChartOption = Parameters<EChartsInstance["setOption"]>[0];

interface EChartProps {
  option: ChartOption;
  height?: number;
  className?: string;
  ariaLabel?: string;
}

/**
 * Thin React wrapper over ECharts: init once, swap options on change,
 * resize with its container, dispose on unmount. Chart *selection* and
 * all numbers come from the backend — this only renders them.
 */
export function EChart({ option, height = 268, className, ariaLabel }: EChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<EChartsInstance | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const chart = echarts.init(container, undefined, { renderer: "canvas" });
    chartRef.current = chart;
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(container);
    return () => {
      observer.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    chartRef.current?.setOption(option, { notMerge: true });
  }, [option]);

  return (
    <div
      ref={containerRef}
      role="img"
      aria-label={ariaLabel ?? "Chart"}
      className={cn("w-full", className)}
      style={{ height }}
    />
  );
}
