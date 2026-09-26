import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  BarChart3,
  Brain,
  CheckCircle2,
  Database,
  Info,
  RefreshCw,
  Sparkles,
  TrendingUp,
} from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState, ErrorState, LoadingState } from "@/components/shared/async-state";
import { PriorityBadge, StatTile } from "@/components/shared/kpi-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { EChart } from "@/components/charts/echart";
import { useChartTheme } from "@/components/charts/chart-theme";
import { barChartOption, lineChartOption } from "@/components/charts/options";
import { Reveal } from "@/components/motion/motion";
import { useAsync } from "@/hooks/use-async";
import { api } from "@/lib/api/endpoints";
import type { UnifiedReport } from "@/lib/api/types";
import { notifyError, notifySuccess } from "@/lib/notify";
import { useAppStore } from "@/store/app-store";
import { cn, formatCompact, formatNumber, formatRelative, truncate } from "@/lib/utils";

const ANALYSIS_STEPS = [
  "Profiling schema and data quality…",
  "Measuring metrics and trends…",
  "Detecting anomalies and contributions…",
  "Prioritizing findings and evidence…",
  "Interpreting with the AI engine…",
];

function useAnalysisSteps(active: boolean) {
  const [step, setStep] = useState(0);
  useEffect(() => {
    if (!active) {
      setStep(0);
      return;
    }
    const timer = window.setInterval(() => {
      setStep((value) => Math.min(value + 1, ANALYSIS_STEPS.length - 1));
    }, 1400);
    return () => window.clearInterval(timer);
  }, [active]);
  return active ? ANALYSIS_STEPS[step] : "";
}

function CapabilityNote({ label, available, reason }: { label: string; available: boolean; reason?: string | null }) {
  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-lg border px-3 py-2 text-[12.5px]",
        available ? "border-emerald/30 bg-emerald/8 text-emerald" : "border-line bg-surface-sunken text-ink-faint",
      )}
    >
      {available ? <CheckCircle2 className="h-3.5 w-3.5" /> : <Info className="h-3.5 w-3.5" />}
      <span className="font-medium">{label}</span>
      {!available && reason && <span className="truncate text-ink-faint">— {reason}</span>}
    </div>
  );
}

export function AnalyticsPage() {
  const navigate = useNavigate();
  const palette = useChartTheme();

  const datasetsVersion = useAppStore((state) => state.datasetsVersion);
  const bump = useAppStore((state) => state.bumpDatasetsVersion);
  const selectedDatasetId = useAppStore((state) => state.selectedDatasetId);
  const setSelectedDatasetId = useAppStore((state) => state.setSelectedDatasetId);
  const reports = useAppStore((state) => state.reports);
  const cacheReport = useAppStore((state) => state.cacheReport);
  const invalidateReport = useAppStore((state) => state.invalidateReport);

  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  const datasets = useAsync(() => api.listDatasets(), [datasetsVersion]);
  const items = useMemo(
    () => (datasets.data?.datasets ?? []).filter((item) => item.status === "ready"),
    [datasets.data],
  );

  const activeId = selectedDatasetId ?? items[0]?.id ?? null;
  const cached = activeId ? (reports[activeId] ?? null) : null;

  const detail = useAsync(
    () => (activeId ? api.getDataset(activeId) : Promise.resolve(null)),
    [activeId, datasetsVersion],
    { enabled: Boolean(activeId) },
  );

  const report: UnifiedReport | null = useMemo(() => {
    if (cached) return cached;
    const fromDetail = detail.data?.currentReport ?? null;
    if (fromDetail && fromDetail.dataset.dataset_id === activeId) return fromDetail;
    return null;
  }, [activeId, cached, detail.data]);

  const needsRun = Boolean(activeId) && !report;

  const runAnalysis = useCallback(
    async (id: string, manual = true) => {
      setRunning(true);
      setRunError(null);
      try {
        const { report: fresh } = await api.analyzeDataset(id);
        if (fresh.status !== "success") {
          setRunError(fresh.error || "The analysis pipeline could not complete for this dataset.");
          if (manual) notifyError(new Error(fresh.error || "Analysis failed."));
          return;
        }
        cacheReport(id, fresh);
        invalidateReport(id);
        bump();
        if (manual) notifySuccess("Analysis complete", "Charts, evidence and insights refreshed.");
      } catch (caught) {
        setRunError(caught instanceof Error ? caught.message : "Analysis failed.");
        notifyError(caught);
      } finally {
        setRunning(false);
      }
    },
    [bump, cacheReport, invalidateReport],
  );

  // Auto-run once when a ready dataset has no report yet.
  useEffect(() => {
    if (needsRun && !running && !runError && detail.data && !detail.loading) {
      void runAnalysis(activeId as string, false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [needsRun, detail.data, running, runError]);

  const stepLabel = useAnalysisSteps(running || (needsRun && !runError));

  const trendOption = useMemo(() => {
    const series = report?.trends.data?.monthly ?? [];
    const moving = report?.trends.data?.moving_average ?? [];
    const hasMoving = moving.some((point) => point.moving_average !== null);
    return lineChartOption({
      categories: series.map((point) => point.period),
      series: [
        { name: report?.trends.data?.measure_column ?? "Measure", data: series.map((p) => p.value), color: palette.series[0] },
        ...(hasMoving
          ? [{ name: "Moving average", data: moving.map((p) => p.moving_average), color: palette.series[2] }]
          : []),
      ],
      palette,
      formatValue: (value) => formatCompact(value),
    });
  }, [palette, report]);

  const contributionOption = useMemo(() => {
    const breakdown = report?.contribution.data?.breakdown ?? [];
    return barChartOption({
      categories: breakdown.map((row) => row.category),
      values: breakdown.map((row) => row.value),
      palette,
      horizontal: true,
      formatValue: (value) => formatCompact(value),
      color: palette.series[1],
    });
  }, [palette, report]);

  const metricsEntries = useMemo(
    () => Object.entries(report?.metrics.data ?? {}),
    [report],
  );

  if (datasets.loading && !datasets.data) return <LoadingState variant="page" />;

  if (datasets.error && !datasets.data) {
    return <ErrorState error={datasets.error} onRetry={datasets.reload} />;
  }

  if (items.length === 0) {
    return (
      <div className="space-y-6">
        <PageHeader
          title="Analytics"
          description="Charts, metrics and evidence for any dataset in this workspace."
        />
        <EmptyState
          icon={
            <div className="flex h-12 w-12 items-center justify-center rounded-xl border border-line-strong bg-surface-raised text-ink-muted">
              <BarChart3 className="h-5 w-5" />
            </div>
          }
          title="No analyzable datasets"
          description="Upload a CSV or Excel file with numeric measures and VISORA will build the full analysis: metrics, trends, contributions, anomalies and prioritized findings."
          action={
            <Button variant="primary" onClick={() => navigate("/datasets?upload=1")}>
              Upload dataset
            </Button>
          }
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Analytics"
        description="Every number below is computed by the VISORA pipeline — sampled from your data, never invented."
        meta={
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="accent">
              <Database className="h-3 w-3" />
              {items.length} analyzable dataset{items.length === 1 ? "" : "s"}
            </Badge>
            {report && (
              <Badge variant="neutral">
                generated {report.generated_at ? formatRelative(report.generated_at) : "just now"}
              </Badge>
            )}
          </div>
        }
        actions={
          <>
            <div className="w-[220px]">
              <Select value={activeId ?? ""} onValueChange={(value) => setSelectedDatasetId(value || null)}>
                <SelectTrigger aria-label="Choose dataset to analyze">
                  <SelectValue placeholder="Select dataset" />
                </SelectTrigger>
                <SelectContent>
                  {items.map((dataset) => (
                    <SelectItem key={dataset.id} value={dataset.id}>
                      {dataset.displayName}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button
              variant="secondary"
              size="md"
              onClick={() => activeId && void runAnalysis(activeId)}
              loading={running}
              disabled={!activeId}
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Re-run
            </Button>
          </>
        }
      />

      {detail.error && !detail.data && (
        <ErrorState error={detail.error} onRetry={detail.reload} />
      )}

      {(running || (needsRun && !runError)) && (
        <Card className="relative overflow-hidden">
          <div
            aria-hidden
            className="pointer-events-none absolute inset-0 opacity-40"
            style={{ backgroundImage: "var(--gradient-accent)", maskImage: "linear-gradient(90deg, transparent, #000 30%, transparent)" }}
          />
          <CardContent className="relative flex flex-wrap items-center gap-4 py-6">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-accent/30 bg-accent-soft text-accent">
              <Sparkles className="h-5 w-5 animate-pulse-soft" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-ink">Running the unified analysis…</p>
              <p className="text-[13px] text-ink-muted">{stepLabel}</p>
            </div>
            <div className="h-1.5 w-40 overflow-hidden rounded-full bg-surface-sunken">
              <div className="shimmer h-full w-full bg-[length:200%_100%]" />
            </div>
          </CardContent>
        </Card>
      )}

      {runError && (
        <ErrorState
          error={new Error(runError)}
          title="Analysis didn't complete"
          onRetry={() => activeId && void runAnalysis(activeId)}
        />
      )}

      {!running && !needsRun && report && (
        <>
          <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {metricsEntries.slice(0, 4).map(([name, entry], index) => (
              <Reveal key={name} delay={index * 0.05}>
                <Card className="h-full">
                  <CardContent className="pt-5">
                    <p className="text-[11.5px] font-medium uppercase tracking-[0.09em] text-ink-faint">
                      {name}
                    </p>
                    <p className="mt-2 text-[24px] font-semibold leading-none tabular text-ink">
                      {formatCompact(entry.sum)}
                    </p>
                    <div className="mt-3 flex flex-wrap gap-1.5 text-[11.5px] text-ink-faint">
                      <span>avg {formatCompact(entry.average)}</span>
                      <span>·</span>
                      <span>min {formatCompact(entry.min)}</span>
                      <span>·</span>
                      <span>max {formatCompact(entry.max)}</span>
                    </div>
                  </CardContent>
                </Card>
              </Reveal>
            ))}
            {metricsEntries.length === 0 && (
              <div className="col-span-full rounded-xl border border-dashed border-line px-5 py-6 text-center text-[13px] text-ink-muted">
                No numeric measures were detected in this dataset.
              </div>
            )}
          </section>

          <div className="flex flex-wrap gap-2">
            <CapabilityNote
              label="Metrics"
              available={report.metrics.available}
              reason={report.metrics.reason}
            />
            <CapabilityNote
              label="Trends"
              available={report.trends.available}
              reason={report.trends.reason}
            />
            <CapabilityNote
              label="Contribution"
              available={report.contribution.available}
              reason={report.contribution.reason}
            />
            <CapabilityNote
              label="Anomalies"
              available={report.anomalies.available}
              reason={report.anomalies.reason}
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <Reveal className="lg:col-span-2">
              <Card className="h-full">
                <CardHeader>
                  <div>
                    <CardTitle>Trend</CardTitle>
                    <CardDescription>
                      {report.trends.data
                        ? `${report.trends.data.measure_column} by ${report.trends.data.date_column}`
                        : "Unavailable for this dataset"}
                    </CardDescription>
                  </div>
                  <Badge variant={report.trends.available ? "accent" : "neutral"}>
                    <TrendingUp className="h-3 w-3" />
                    {report.trends.data?.monthly.length ?? 0} periods
                  </Badge>
                </CardHeader>
                <CardContent>
                  {report.trends.available && report.trends.data && report.trends.data.monthly.length > 0 ? (
                    <EChart option={trendOption} height={288} ariaLabel="Trend chart" />
                  ) : (
                    <div className="flex h-[288px] flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-line px-6 text-center">
                      <TrendingUp className="h-5 w-5 text-ink-faint" />
                      <p className="text-sm text-ink-muted">
                        {report.trends.reason ?? "Trend analysis isn't available here."}
                      </p>
                    </div>
                  )}

                  {report.trends.data?.period_comparison.available && (
                    <div className="mt-4 grid gap-3 sm:grid-cols-4">
                      <StatTile label="Previous" value={report.trends.data.period_comparison.previous_period ?? "—"} />
                      <StatTile label="Current" value={report.trends.data.period_comparison.current_period ?? "—"} />
                      <StatTile
                        label="Change"
                        value={formatNumber(report.trends.data.period_comparison.change)}
                      />
                      <StatTile
                        label="Change %"
                        value={
                          report.trends.data.period_comparison.change_percent === null
                            ? "—"
                            : `${report.trends.data.period_comparison.change_percent}%`
                        }
                      />
                    </div>
                  )}
                </CardContent>
              </Card>
            </Reveal>

            <Reveal delay={0.08}>
              <Card className="h-full">
                <CardHeader>
                  <div>
                    <CardTitle>Findings</CardTitle>
                    <CardDescription>Prioritized by impact, backed by evidence</CardDescription>
                  </div>
                  <Badge variant={report.prioritized_findings.some((f) => f.priority === "critical") ? "danger" : "neutral"}>
                    {report.prioritized_findings.length} total
                  </Badge>
                </CardHeader>
                <CardContent className="pt-4">
                  <div className="max-h-[340px] space-y-3 overflow-y-auto pr-1">
                    {report.prioritized_findings.map((finding) => (
                      <div
                        key={finding.id}
                        className="rounded-lg border border-line bg-surface-sunken px-3.5 py-3 transition-colors hover:border-line-strong"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <p className="text-[13px] font-medium leading-snug text-ink">
                            {truncate(finding.title, 90)}
                          </p>
                          <PriorityBadge priority={finding.priority} />
                        </div>
                        <p className="mt-1.5 text-[11.5px] text-ink-faint">
                          {finding.type} · {finding.source}
                          {finding.period ? ` · ${finding.period}` : ""}
                          {finding.value !== null ? ` · ${formatCompact(finding.value)}` : ""}
                        </p>
                      </div>
                    ))}
                    {report.prioritized_findings.length === 0 && (
                      <p className="text-[13px] text-ink-muted">
                        No prioritized findings — this dataset looks clean.
                      </p>
                    )}
                  </div>
                </CardContent>
              </Card>
            </Reveal>
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <Reveal delay={0.12} className="lg:col-span-2">
              <Card className="h-full">
                <CardHeader>
                  <div>
                    <CardTitle>Contribution</CardTitle>
                    <CardDescription>
                      {report.contribution.data
                        ? `${report.contribution.data.measure} by ${report.contribution.data.dimension}`
                        : "Unavailable for this dataset"}
                    </CardDescription>
                  </div>
                  <Badge variant="neutral">
                    {report.contribution.data?.total_categories ?? 0} categories
                  </Badge>
                </CardHeader>
                <CardContent>
                  {report.contribution.available && report.contribution.data ? (
                    <EChart option={contributionOption} height={276} ariaLabel="Contribution chart" />
                  ) : (
                    <div className="flex h-[276px] items-center justify-center rounded-lg border border-dashed border-line px-6 text-center text-sm text-ink-muted">
                      {report.contribution.reason ?? "Contribution isn't available here."}
                    </div>
                  )}
                </CardContent>
              </Card>
            </Reveal>

            <Reveal delay={0.16}>
              <Card className="h-full">
                <CardHeader>
                  <div>
                    <CardTitle>Anomalies</CardTitle>
                    <CardDescription>Rows that break their own baseline</CardDescription>
                  </div>
                  <Badge variant={report.anomalies.available ? "warning" : "neutral"}>
                    <AlertTriangle className="h-3 w-3" />
                    {Object.values(report.anomalies.data ?? {}).reduce(
                      (total, rows) => total + rows.length,
                      0,
                    )}{" "}
                    detected
                  </Badge>
                </CardHeader>
                <CardContent className="pt-4">
                  {report.anomalies.available && report.anomalies.data ? (
                    <div className="max-h-[300px] space-y-3 overflow-y-auto pr-1">
                      {Object.entries(report.anomalies.data).map(([metric, rows]) =>
                        rows.slice(0, 4).map((row) => (
                          <div
                            key={`${metric}-${row.row_id}`}
                            className="rounded-lg border border-line bg-surface-sunken px-3.5 py-3"
                          >
                            <div className="flex items-center justify-between gap-3">
                              <p className="text-[13px] font-medium text-ink">{row.metric}</p>
                              <Badge variant="warning" className="mono">
                                z {row.z_score.toFixed(2)}
                              </Badge>
                            </div>
                            <p className="mt-1 text-[12px] text-ink-muted">{row.reason}</p>
                            <p className="mono mt-1 text-[11.5px] text-ink-faint">
                              value {formatCompact(row.value)} · baseline {formatCompact(row.baseline)}
                            </p>
                          </div>
                        )),
                      )}
                    </div>
                  ) : (
                    <div className="flex h-[220px] flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-line text-center">
                      <CheckCircle2 className="h-5 w-5 text-emerald" />
                      <p className="text-sm text-ink-muted">
                        {report.anomalies.reason ?? "No anomalies detected."}
                      </p>
                    </div>
                  )}
                </CardContent>
              </Card>
            </Reveal>
          </div>

          <Reveal delay={0.2}>
            <Card>
              <CardHeader>
                <div className="flex items-center gap-2">
                  <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-accent/30 bg-accent-soft text-accent">
                    <Brain className="h-4 w-4" />
                  </span>
                  <div>
                    <CardTitle>AI interpretation</CardTitle>
                    <CardDescription>
                      {report.ai_analysis.source === "ai"
                        ? `Generated with ${report.ai_analysis.provider_used ?? "an AI provider"}`
                        : "Local analytical fallback — no provider was available"}
                    </CardDescription>
                  </div>
                </div>
                <Button variant="ghost" size="sm" onClick={() => navigate("/insights")}>
                  Open insights
                </Button>
              </CardHeader>
              <CardContent className="pt-4">
                <p className="text-[13.5px] leading-relaxed text-ink-muted">
                  {report.ai_analysis.summary || "No interpretation was produced for this dataset."}
                </p>
                <div className="mt-4 flex flex-wrap gap-1.5">
                  {report.capabilities &&
                    Object.entries(report.capabilities).map(([key, capability]) => (
                      <Badge key={key} variant={capability.available ? "success" : "neutral"}>
                        {key}: {capability.available ? "available" : "unavailable"}
                      </Badge>
                    ))}
                </div>
              </CardContent>
            </Card>
          </Reveal>
        </>
      )}
    </div>
  );
}
