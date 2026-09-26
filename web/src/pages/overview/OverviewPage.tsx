import { useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  Database,
  FileText,
  Layers,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  TrendingUp,
} from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { KpiCard, PriorityBadge } from "@/components/shared/kpi-card";
import { EmptyState, ErrorState, LoadingState } from "@/components/shared/async-state";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EChart } from "@/components/charts/echart";
import { useChartTheme } from "@/components/charts/chart-theme";
import { barChartOption, lineChartOption } from "@/components/charts/options";
import { Reveal, Stagger, StaggerItem } from "@/components/motion/motion";
import { BrandLockup } from "@/components/brand/logo";
import { useAsync } from "@/hooks/use-async";
import { api } from "@/lib/api/endpoints";
import { useAppStore } from "@/store/app-store";
import { formatCompact, formatNumber, formatRelative, truncate } from "@/lib/utils";

const KPI_ICONS: Record<string, typeof Database> = {
  rows: Database,
  columns: Layers,
  findings: AlertTriangle,
  quality: ShieldCheck,
};

export function OverviewPage() {
  const navigate = useNavigate();
  const datasetsVersion = useAppStore((state) => state.datasetsVersion);
  const palette = useChartTheme();

  const { data: overview, loading, error, reload } = useAsync(
    () => api.overview(),
    [datasetsVersion],
  );

  const trendOption = useMemo(() => {
    const series = overview?.trend?.series ?? [];
    return lineChartOption({
      categories: series.map((point) => point.period),
      series: [
        {
          name: overview?.trend?.measure ?? "Value",
          data: series.map((point) => point.value),
          color: palette.series[0],
        },
      ],
      palette,
      formatValue: (value) => formatCompact(value),
    });
  }, [overview, palette]);

  const contributionOption = useMemo(() => {
    const series = overview?.contribution?.series ?? [];
    return barChartOption({
      categories: series.map((item) => item.label),
      values: series.map((item) => item.value),
      palette,
      horizontal: true,
      formatValue: (value) => formatCompact(value),
      color: palette.series[1],
    });
  }, [overview, palette]);

  if (loading && !overview) return <LoadingState variant="page" />;
  if (error && !overview) return <ErrorState error={error} onRetry={reload} />;

  const isEmpty = !overview || overview.datasets.total === 0;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Overview"
        description="What deserves your attention today — computed from your data, not guessed."
        actions={
          <>
            <Button variant="secondary" size="md" onClick={reload} loading={loading}>
              <RefreshCw className="h-3.5 w-3.5" />
              Refresh
            </Button>
            <Button variant="primary" size="md" onClick={() => navigate("/datasets?upload=1")}>
              Upload dataset
            </Button>
          </>
        }
      />

      {isEmpty ? (
        <EmptyState
          icon={
            <div className="relative">
              <BrandLockup />
            </div>
          }
          title="Make the hidden obvious"
          description="Upload a CSV or Excel file and VISORA will profile it, analyze it, and surface the trends, anomalies and evidence worth acting on."
          action={
            <Button variant="primary" size="lg" onClick={() => navigate("/datasets?upload=1")}>
              Upload your first dataset
              <ArrowRight className="h-4 w-4" />
            </Button>
          }
          secondaryAction={
            <Button variant="ghost" size="lg" onClick={() => navigate("/reports")}>
              Browse reports
            </Button>
          }
        />
      ) : (
        <>
          <Stagger className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {(overview?.kpis ?? []).map((kpi, index) => {
              const Icon = KPI_ICONS[kpi.id] ?? TrendingUp;
              return (
                <StaggerItem key={kpi.id}>
                  <KpiCard
                    label={kpi.label}
                    value={kpi.value}
                    format={kpi.format}
                    tone={kpi.tone}
                    delay={index * 0.05}
                    icon={<Icon className="h-4 w-4" />}
                    hint={
                      kpi.id === "rows"
                        ? `${overview?.datasets.ready ?? 0} dataset(s) ready`
                        : kpi.id === "findings"
                          ? `${overview?.findings.total ?? 0} total findings`
                          : undefined
                    }
                  />
                </StaggerItem>
              );
            })}
          </Stagger>

          <div className="grid gap-4 lg:grid-cols-3">
            <Reveal delay={0.08} className="lg:col-span-2">
              <Card className="h-full">
                <CardHeader>
                  <div>
                    <CardTitle>Trend over time</CardTitle>
                    <CardDescription>
                      {overview?.trend.available
                        ? `${overview.trend.measure ?? "Measure"} by ${overview.trend.dateColumn ?? "period"}`
                        : "No trend capability for this dataset"}
                    </CardDescription>
                  </div>
                  <Badge variant="accent">
                    <TrendingUp className="h-3 w-3" />
                    {overview?.trend.series.length ?? 0} periods
                  </Badge>
                </CardHeader>
                <CardContent>
                  {overview?.trend.available && overview.trend.series.length > 0 ? (
                    <EChart option={trendOption} height={276} ariaLabel="Trend over time chart" />
                  ) : (
                    <div className="flex h-[276px] flex-col items-center justify-center gap-2 rounded-lg border border-line bg-surface-sunken px-6 text-center">
                      <TrendingUp className="h-5 w-5 text-ink-faint" />
                      <p className="text-sm text-ink-muted">
                        Trends need a date column and a numeric measure.
                      </p>
                      <p className="text-xs text-ink-faint">
                        VISORA keeps this unavailable rather than inventing a pattern.
                      </p>
                    </div>
                  )}
                </CardContent>
              </Card>
            </Reveal>

            <Reveal delay={0.14}>
              <Card className="h-full">
                <CardHeader>
                  <div>
                    <CardTitle>Priority findings</CardTitle>
                    <CardDescription>Highest-impact evidence first</CardDescription>
                  </div>
                </CardHeader>
                <CardContent className="pt-4">
                  {overview && overview.findings.items.length > 0 ? (
                    <div className="space-y-3">
                      {overview.findings.items.map((finding) => (
                        <div
                          key={finding.id}
                          className="group rounded-lg border border-line bg-surface-sunken px-3.5 py-3 transition-colors hover:border-line-strong"
                        >
                          <div className="flex items-start justify-between gap-3">
                            <p className="text-[13px] font-medium leading-snug text-ink">
                              {truncate(finding.title, 78)}
                            </p>
                            <PriorityBadge priority={finding.priority} />
                          </div>
                          <p className="mt-1.5 text-[11.5px] text-ink-faint">
                            {finding.type} · {finding.source}
                            {finding.period ? ` · ${finding.period}` : ""}
                          </p>
                        </div>
                      ))}
                      <Link
                        to="/insights"
                        className="inline-flex items-center gap-1.5 pt-1 text-[13px] font-medium text-accent transition-colors hover:text-ink"
                      >
                        See all {overview.findings.total} findings
                        <ArrowRight className="h-3.5 w-3.5" />
                      </Link>
                    </div>
                  ) : (
                    <div className="flex h-[220px] flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-line text-center">
                      <ShieldCheck className="h-5 w-5 text-emerald" />
                      <p className="text-sm text-ink-muted">No critical findings yet.</p>
                      <p className="text-xs text-ink-faint">
                        Run an analysis to surface evidence-backed insights.
                      </p>
                    </div>
                  )}
                </CardContent>
              </Card>
            </Reveal>
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <Reveal delay={0.18} className="lg:col-span-2">
              <Card className="h-full">
                <CardHeader>
                  <div>
                    <CardTitle>Contribution</CardTitle>
                    <CardDescription>
                      {overview?.contribution.available
                        ? `${overview.contribution.measure ?? "Measure"} by ${overview.contribution.dimension ?? "dimension"}`
                        : "Category contribution is unavailable for this data"}
                    </CardDescription>
                  </div>
                </CardHeader>
                <CardContent>
                  {overview?.contribution.available && overview.contribution.series.length > 0 ? (
                    <EChart
                      option={contributionOption}
                      height={264}
                      ariaLabel="Contribution by category chart"
                    />
                  ) : (
                    <div className="flex h-[264px] items-center justify-center rounded-lg border border-dashed border-line px-6 text-center text-sm text-ink-muted">
                      Contribution analysis needs at least one categorical dimension.
                    </div>
                  )}
                </CardContent>
              </Card>
            </Reveal>

            <Reveal delay={0.22}>
              <Card className="relative h-full overflow-hidden">
                <div
                  aria-hidden
                  className="pointer-events-none absolute -right-16 -top-16 h-44 w-44 rounded-full opacity-30 blur-3xl"
                  style={{ backgroundImage: "var(--gradient-accent)" }}
                />
                <CardHeader>
                  <div className="flex items-center gap-2">
                    <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-accent/30 bg-accent-soft text-accent">
                      <Sparkles className="h-4 w-4" />
                    </span>
                    <div>
                      <CardTitle>AI interpretation</CardTitle>
                      <CardDescription>
                        {overview?.insights.source === "ai"
                          ? "Provider-grounded"
                          : "Local evidence fallback"}
                      </CardDescription>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="pt-4">
                  <p className="text-[13px] leading-relaxed text-ink-muted">
                    {overview?.insights.summary
                      ? truncate(overview.insights.summary, 260)
                      : "No interpretation available yet."}
                  </p>
                  <div className="mt-4 flex items-center justify-between">
                    <Badge variant={overview?.insights.source === "ai" ? "accent" : "neutral"}>
                      {overview?.insights.count ?? 0} insights
                    </Badge>
                    <Link
                      to="/insights"
                      className="inline-flex items-center gap-1.5 text-[13px] font-medium text-accent transition-colors hover:text-ink"
                    >
                      Open AI Insights
                      <ArrowRight className="h-3.5 w-3.5" />
                    </Link>
                  </div>
                </CardContent>
              </Card>
            </Reveal>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Reveal delay={0.26}>
              <Card>
                <CardHeader>
                  <div>
                    <CardTitle>Recent datasets</CardTitle>
                    <CardDescription>Latest uploads in this workspace</CardDescription>
                  </div>
                  <Button variant="ghost" size="sm" onClick={() => navigate("/datasets")}>
                    View all
                    <ArrowRight className="h-3.5 w-3.5" />
                  </Button>
                </CardHeader>
                <CardContent className="pt-4">
                  <div className="space-y-2">
                    {(overview?.datasets.recent ?? []).map((dataset) => (
                      <button
                        key={dataset.id}
                        type="button"
                        onClick={() => navigate(`/datasets/${dataset.id}`)}
                        className="flex w-full items-center gap-3 rounded-lg border border-line bg-surface-sunken px-3.5 py-3 text-left transition-all hover:border-line-strong hover:bg-surface-hover"
                      >
                        <span
                          className={
                            dataset.status === "ready"
                              ? "h-1.5 w-1.5 shrink-0 rounded-full bg-emerald"
                              : "h-1.5 w-1.5 shrink-0 rounded-full bg-amber"
                          }
                        />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[13.5px] font-medium text-ink">
                            {dataset.displayName}
                          </span>
                          <span className="mono block text-[11.5px] text-ink-faint">
                            {formatNumber(dataset.rowCount)} rows ·{" "}
                            {formatNumber(dataset.columnCount)} cols ·{" "}
                            {formatRelative(dataset.createdAt)}
                          </span>
                        </span>
                        <ArrowRight className="h-3.5 w-3.5 shrink-0 text-ink-faint" />
                      </button>
                    ))}
                  </div>
                </CardContent>
              </Card>
            </Reveal>

            <Reveal delay={0.3}>
              <Card>
                <CardHeader>
                  <div>
                    <CardTitle>Reports</CardTitle>
                    <CardDescription>Generated, downloadable, evidence-backed</CardDescription>
                  </div>
                  <Button variant="ghost" size="sm" onClick={() => navigate("/reports")}>
                    Manage
                    <ArrowRight className="h-3.5 w-3.5" />
                  </Button>
                </CardHeader>
                <CardContent className="pt-4">
                  <div className="grid grid-cols-2 gap-3">
                    <div className="rounded-lg border border-line bg-surface-sunken px-3.5 py-3">
                      <FileText className="h-4 w-4 text-ink-faint" />
                      <p className="mt-2 text-xl font-semibold tabular text-ink">
                        {overview?.reports.reports.length ?? 0}
                      </p>
                      <p className="text-[11.5px] text-ink-faint">TXT reports</p>
                    </div>
                    <div className="rounded-lg border border-line bg-surface-sunken px-3.5 py-3">
                      <Database className="h-4 w-4 text-ink-faint" />
                      <p className="mt-2 text-xl font-semibold tabular text-ink">
                        {overview?.reports.current ? 1 : 0}
                      </p>
                      <p className="text-[11.5px] text-ink-faint">Unified snapshot</p>
                    </div>
                  </div>
                  <p className="mt-3 text-[12px] leading-relaxed text-ink-faint">
                    Every report traces back to evidence in your data — generated{" "}
                    <span className="text-ink-muted">
                      {overview?.generatedAt ? formatRelative(overview.generatedAt) : "—"}
                    </span>
                    .
                  </p>
                </CardContent>
              </Card>
            </Reveal>
          </div>
        </>
      )}
    </div>
  );
}
