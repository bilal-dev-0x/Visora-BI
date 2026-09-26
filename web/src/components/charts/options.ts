import type { ChartOption } from "./echart";
import type { ChartPalette } from "./chart-theme";

/** #rrggbb → rgba() for area fills. */
export function withAlpha(hex: string, alpha: number): string {
  const normalized = hex.replace("#", "");
  if (normalized.length !== 6) return hex;
  const r = parseInt(normalized.slice(0, 2), 16);
  const g = parseInt(normalized.slice(2, 4), 16);
  const b = parseInt(normalized.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function axisTooltip(palette: ChartPalette) {
  return {
    trigger: "axis" as const,
    backgroundColor: palette.surface,
    borderColor: palette.line,
    borderWidth: 1,
    padding: [8, 11] as [number, number],
    textStyle: { color: palette.ink, fontSize: 12 },
    extraCssText: "border-radius: 8px; box-shadow: 0 12px 32px -12px rgba(0,0,0,0.55);",
    axisPointer: {
      type: "line" as const,
      lineStyle: { color: palette.lineStrong, type: "solid" as const },
    },
  };
}

function baseGrid() {
  return { left: 6, right: 10, top: 18, bottom: 2, containLabel: true };
}

export interface LineSeriesInput {
  name: string;
  data: (number | null)[];
  color?: string;
}

export function lineChartOption({
  categories,
  series,
  palette,
  area = true,
  formatValue,
  smooth = 0.35,
}: {
  categories: string[];
  series: LineSeriesInput[];
  palette: ChartPalette;
  area?: boolean;
  formatValue?: (value: number) => string;
  smooth?: number;
}): ChartOption {
  return {
    animationDuration: 650,
    animationEasing: "cubicOut",
    grid: baseGrid(),
    tooltip: {
      ...axisTooltip(palette),
      valueFormatter: formatValue
        ? (value: unknown) => (typeof value === "number" ? formatValue(value) : "—")
        : undefined,
    },
    xAxis: {
      type: "category",
      data: categories,
      boundaryGap: false,
      axisLine: { lineStyle: { color: palette.line } },
      axisTick: { show: false },
      axisLabel: { color: palette.inkFaint, fontSize: 11, hideOverlap: true },
    },
    yAxis: {
      type: "value",
      splitLine: { lineStyle: { color: palette.line } },
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: palette.inkFaint,
        fontSize: 11,
        formatter: formatValue ? (value: number) => formatValue(value) : undefined,
      },
    },
    series: series.map((item, index) => {
      const color = item.color ?? palette.series[index % palette.series.length];
      return {
        name: item.name,
        type: "line" as const,
        data: item.data,
        smooth,
        symbol: "circle",
        symbolSize: 6,
        showSymbol: false,
        connectNulls: true,
        lineStyle: { width: 2.25, color },
        itemStyle: { color },
        emphasis: { focus: "series" as const },
        areaStyle: area
          ? {
              color: {
                type: "linear",
                x: 0,
                y: 0,
                x2: 0,
                y2: 1,
                colorStops: [
                  { offset: 0, color: withAlpha(color, 0.26) },
                  { offset: 1, color: withAlpha(color, 0) },
                ],
              },
            }
          : undefined,
      };
    }),
  };
}

export function barChartOption({
  categories,
  values,
  palette,
  horizontal = false,
  formatValue,
  color,
}: {
  categories: string[];
  values: (number | null)[];
  palette: ChartPalette;
  horizontal?: boolean;
  formatValue?: (value: number) => string;
  color?: string;
}): ChartOption {
  const barColor = color ?? palette.series[1];

  if (horizontal) {
    return {
      animationDuration: 650,
      animationEasing: "cubicOut",
      grid: { left: 6, right: 24, top: 6, bottom: 2, containLabel: true },
      tooltip: {
        trigger: "axis" as const,
        backgroundColor: palette.surface,
        borderColor: palette.line,
        borderWidth: 1,
        textStyle: { color: palette.ink, fontSize: 12 },
        extraCssText: "border-radius: 8px; box-shadow: 0 12px 32px -12px rgba(0,0,0,0.55);",
        axisPointer: { type: "shadow" as const },
        valueFormatter: formatValue
          ? (value: unknown) => (typeof value === "number" ? formatValue(value) : "—")
          : undefined,
      },
      xAxis: {
        type: "value",
        splitLine: { lineStyle: { color: palette.line } },
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: palette.inkFaint, fontSize: 11 },
      },
      yAxis: {
        type: "category",
        data: categories,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: palette.inkMuted, fontSize: 11.5, width: 128, overflow: "truncate" },
      },
      series: [
        {
          type: "bar" as const,
          data: values,
          barWidth: "58%",
          itemStyle: {
            color: {
              type: "linear",
              x: 0,
              y: 0,
              x2: 1,
              y2: 0,
              colorStops: [
                { offset: 0, color: withAlpha(barColor, 0.55) },
                { offset: 1, color: barColor },
              ],
            },
            borderRadius: [0, 6, 6, 0],
          },
          emphasis: { itemStyle: { color: barColor } },
        },
      ],
    };
  }

  return {
    animationDuration: 650,
    animationEasing: "cubicOut",
    grid: baseGrid(),
    tooltip: {
      trigger: "axis" as const,
      backgroundColor: palette.surface,
      borderColor: palette.line,
      borderWidth: 1,
      textStyle: { color: palette.ink, fontSize: 12 },
      extraCssText: "border-radius: 8px; box-shadow: 0 12px 32px -12px rgba(0,0,0,0.55);",
      axisPointer: { type: "shadow" as const },
      valueFormatter: formatValue
        ? (value: unknown) => (typeof value === "number" ? formatValue(value) : "—")
        : undefined,
    },
    xAxis: {
      type: "category",
      data: categories,
      axisLine: { lineStyle: { color: palette.line } },
      axisTick: { show: false },
      axisLabel: { color: palette.inkFaint, fontSize: 11, hideOverlap: true },
    },
    yAxis: {
      type: "value",
      splitLine: { lineStyle: { color: palette.line } },
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: palette.inkFaint, fontSize: 11 },
    },
    series: [
      {
        type: "bar" as const,
        data: values,
        barMaxWidth: 34,
        itemStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: barColor },
              { offset: 1, color: withAlpha(barColor, 0.45) },
            ],
          },
          borderRadius: [6, 6, 0, 0],
        },
      },
    ],
  };
}

export function donutChartOption({
  items,
  palette,
  formatValue,
  centerLabel,
  centerSublabel,
}: {
  items: { name: string; value: number; color?: string }[];
  palette: ChartPalette;
  formatValue?: (value: number) => string;
  centerLabel?: string;
  centerSublabel?: string;
}): ChartOption {
  return {
    animationDuration: 700,
    animationEasing: "cubicOut",
    tooltip: {
      trigger: "item" as const,
      backgroundColor: palette.surface,
      borderColor: palette.line,
      borderWidth: 1,
      textStyle: { color: palette.ink, fontSize: 12 },
      extraCssText: "border-radius: 8px; box-shadow: 0 12px 32px -12px rgba(0,0,0,0.55);",
      formatter: (params: { name: string; value: number; percent: number }) =>
        `${params.name}<br/><b>${formatValue ? formatValue(params.value) : params.value}</b> · ${params.percent}%`,
    },
    legend: {
      bottom: 0,
      icon: "circle",
      itemWidth: 8,
      itemHeight: 8,
      textStyle: { color: palette.inkMuted, fontSize: 11.5 },
    },
    series: [
      {
        type: "pie" as const,
        radius: ["64%", "86%"],
        center: ["50%", "44%"],
        avoidLabelOverlap: true,
        padAngle: 2,
        itemStyle: { borderRadius: 6, borderColor: palette.surface, borderWidth: 2 },
        label: {
          show: true,
          position: "center",
          formatter: centerLabel ? `${centerLabel}\n${centerSublabel ?? ""}` : "",
          textStyle: { color: palette.ink, fontSize: 17, fontWeight: 600, lineHeight: 22 },
        },
        emphasis: {
          scaleSize: 4,
          itemStyle: { shadowBlur: 16, shadowColor: "rgba(0,0,0,0.35)" },
        },
        data: items.map((item, index) => ({
          ...item,
          color: item.color ?? palette.series[index % palette.series.length],
        })),
      },
    ],
  };
}
