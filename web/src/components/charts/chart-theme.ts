import { useAppStore } from "@/store/app-store";

export interface ChartPalette {
  ink: string;
  inkMuted: string;
  inkFaint: string;
  line: string;
  lineStrong: string;
  surface: string;
  canvas: string;
  series: string[];
}

function readVar(name: string, fallback: string): string {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

/**
 * Reads the active theme's chart tokens. Subscribing to the theme
 * setting means every chart repaints with the correct palette after an
 * appearance change.
 */
export function useChartTheme(): ChartPalette {
  const theme = useAppStore((state) => state.theme);
  const resolved =
    document.documentElement.dataset.theme ?? (theme === "light" ? "light" : "dark");

  return {
    ink: readVar("--ink", resolved === "light" ? "#13152c" : "#eff0f7"),
    inkMuted: readVar("--ink-muted", resolved === "light" ? "#565b76" : "#979bb4"),
    inkFaint: readVar("--ink-faint", resolved === "light" ? "#868ba4" : "#666b85"),
    line: readVar("--line", resolved === "light" ? "rgba(13,15,40,0.09)" : "rgba(255,255,255,0.075)"),
    lineStrong: readVar(
      "--line-strong",
      resolved === "light" ? "rgba(13,15,40,0.16)" : "rgba(255,255,255,0.14)",
    ),
    surface: readVar("--surface-raised", resolved === "light" ? "#fafbfe" : "#16162f"),
    canvas: readVar("--canvas", resolved === "light" ? "#f5f6fb" : "#08080f"),
    series: [
      readVar("--chart-1", "#22d3ee"),
      readVar("--chart-2", "#6366f1"),
      readVar("--chart-3", "#a78bfa"),
      readVar("--chart-4", "#34d399"),
      readVar("--chart-5", "#fbbf24"),
      readVar("--chart-6", "#f472b6"),
    ],
  };
}
