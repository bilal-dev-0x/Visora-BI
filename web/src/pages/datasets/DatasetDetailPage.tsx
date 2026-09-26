import { useCallback, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { motion } from "motion/react";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  Download,
  Eye,
  Layers,
  Sparkles,
  Table2,
  Trash2,
} from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { StatusBadge } from "@/components/shared/kpi-card";
import { ConfirmationDialog } from "@/components/shared/confirmation-dialog";
import { EmptyState, ErrorState, LoadingState } from "@/components/shared/async-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError } from "@/lib/api/client";
import { useAsync } from "@/hooks/use-async";
import { api } from "@/lib/api/endpoints";
import { notifyError, notifySuccess } from "@/lib/notify";
import { useAppStore } from "@/store/app-store";
import { cn, formatBytes, formatDateTime, formatNumber, formatPercent } from "@/lib/utils";

const PROFILE_REASONS: Record<string, string> = {
  unreadable_file: "This file couldn't be read as a table. It may be corrupted or renamed CSV/Excel content.",
  stored_file_missing: "The stored file is missing from local storage. Try re-uploading it.",
};

export function DatasetDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const datasetsVersion = useAppStore((state) => state.datasetsVersion);
  const bump = useAppStore((state) => state.bumpDatasetsVersion);
  const setSelectedDatasetId = useAppStore((state) => state.setSelectedDatasetId);
  const cacheReport = useAppStore((state) => state.cacheReport);
  const invalidateReport = useAppStore((state) => state.invalidateReport);

  const { data, loading, error, reload } = useAsync(
    () => api.getDataset(id),
    [id, datasetsVersion],
  );
  const [analyzing, setAnalyzing] = useState(false);

  const analyze = useCallback(async () => {
    if (!id) return;
    setAnalyzing(true);
    try {
      const { report } = await api.analyzeDataset(id);
      if (report.status !== "success") {
        notifyError(new Error(report.error || "Analysis could not complete."));
        return;
      }
      cacheReport(id, report);
      invalidateReport(id);
      bump();
      setSelectedDatasetId(id);
      notifySuccess("Analysis ready", "Opening charts, evidence and insights.");
      navigate("/analytics");
    } catch (caught) {
      notifyError(caught);
    } finally {
      setAnalyzing(false);
    }
  }, [bump, cacheReport, id, invalidateReport, navigate, setSelectedDatasetId]);

  const download = useCallback(async () => {
    if (!data) return;
    try {
      await api.downloadReport(id, `${data.dataset.displayName}.txt`);
      notifySuccess("Report downloaded");
    } catch (caught) {
      notifyError(caught);
    }
  }, [data, id]);

  if (loading && !data) return <LoadingState variant="detail" />;

  if (error) {
    if (error instanceof ApiError && error.status === 404) {
      return (
        <EmptyState
          title="Dataset not found"
          description="It may have been deleted from this workspace. Pick another dataset from the sidebar or upload a new file."
          action={
            <Button variant="primary" onClick={() => navigate("/datasets")}>
              Back to datasets
            </Button>
          }
        />
      );
    }
    return <ErrorState error={error} onRetry={reload} />;
  }

  if (!data) return null;

  const { dataset, profile, currentReport } = data;
  const quality = profile.quality;

  return (
    <div className="space-y-6">
      <div>
        <Link
          to="/datasets"
          className="inline-flex items-center gap-1.5 text-[13px] text-ink-muted transition-colors hover:text-ink"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Datasets
        </Link>
      </div>

      <PageHeader
        title={dataset.displayName}
        description={dataset.fileName}
        meta={
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={dataset.status} />
            <Badge variant="neutral">{formatNumber(dataset.rowCount)} rows</Badge>
            <Badge variant="neutral">{formatNumber(dataset.columnCount)} columns</Badge>
            <Badge variant="neutral">{formatBytes(dataset.sizeBytes)}</Badge>
            <Badge variant="outline" className="mono">
              {formatDateTime(dataset.createdAt)}
            </Badge>
          </div>
        }
        actions={
          <>
            <Button
              variant="secondary"
              size="md"
              onClick={download}
              disabled={!dataset.reportAvailable}
              title={dataset.reportAvailable ? undefined : "Run an analysis first"}
            >
              <Download className="h-3.5 w-3.5" />
              Download report
            </Button>
            <ConfirmationDialog
              title={`Delete ${dataset.displayName}?`}
              description="The stored file, analytical table and report are removed permanently."
              confirmLabel="Delete dataset"
              onConfirm={async () => {
                try {
                  await api.deleteDataset(id);
                  invalidateReport(id);
                  bump();
                  notifySuccess("Dataset deleted", `${dataset.displayName} was removed.`);
                  navigate("/datasets");
                } catch (caught) {
                  notifyError(caught);
                }
              }}
              trigger={
                <Button variant="danger" size="md">
                  <Trash2 className="h-3.5 w-3.5" />
                  Delete
                </Button>
              }
            />
            <Button variant="primary" size="md" onClick={() => void analyze()} loading={analyzing}>
              <BarChart3 className="h-3.5 w-3.5" />
              {data.isCurrentAnalysis ? "Re-run analysis" : "Analyze dataset"}
            </Button>
          </>
        }
      />

      {!profile.available && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-start gap-3 rounded-xl border border-amber/35 bg-amber/8 px-4 py-3.5"
        >
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber" />
          <div>
            <p className="text-sm font-medium text-ink">This dataset needs attention</p>
            <p className="mt-0.5 text-[13px] leading-relaxed text-ink-muted">
              {PROFILE_REASONS[profile.reason ?? ""] ??
                "VISORA couldn't profile this file. Try re-uploading a valid CSV or Excel file."}
            </p>
          </div>
        </motion.div>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Tabs defaultValue="overview">
            <TabsList>
              <TabsTrigger value="overview">
                <Layers className="h-3.5 w-3.5" />
                Overview
              </TabsTrigger>
              <TabsTrigger value="preview">
                <Eye className="h-3.5 w-3.5" />
                Preview
              </TabsTrigger>
              <TabsTrigger value="columns">
                <Table2 className="h-3.5 w-3.5" />
                Columns
              </TabsTrigger>
              <TabsTrigger value="statistics">
                <BarChart3 className="h-3.5 w-3.5" />
                Statistics
              </TabsTrigger>
            </TabsList>

            <TabsContent value="overview">
              <Card>
                <CardHeader>
                  <div>
                    <CardTitle>Data quality</CardTitle>
                    <CardDescription>Structural profile from the existing analyzer</CardDescription>
                  </div>
                </CardHeader>
                <CardContent className="pt-4">
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                    <StatTile label="Missing values" value={formatNumber(quality?.missingValues ?? 0)} />
                    <StatTile label="Duplicate rows" value={formatNumber(quality?.duplicateRows ?? 0)} />
                    <StatTile label="Empty rows" value={formatNumber(quality?.emptyRows ?? 0)} />
                    <StatTile
                      label="Affected columns"
                      value={formatNumber(quality?.missingColumns.length ?? 0)}
                    />
                  </div>

                  <div className="mt-5 space-y-2.5">
                    <p className="text-[11.5px] font-medium uppercase tracking-wider text-ink-faint">
                      Column health
                    </p>
                    {profile.columnHealth.length === 0 ? (
                      <p className="text-[13px] text-ink-muted">No missing data detected.</p>
                    ) : (
                      profile.columnHealth.slice(0, 8).map((column) => (
                        <div key={column.Column} className="flex items-center gap-3">
                          <span className="w-40 shrink-0 truncate text-[12.5px] text-ink-muted">
                            {column.Column}
                          </span>
                          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-sunken">
                            <div
                              className={cn(
                                "h-full rounded-full transition-all duration-700",
                                column["Missing Percentage"] > 20
                                  ? "bg-rose"
                                  : column["Missing Percentage"] > 0
                                    ? "bg-amber"
                                    : "bg-emerald",
                              )}
                              style={{ width: `${Math.max(2, column["Missing Percentage"])}%` }}
                            />
                          </div>
                          <span className="w-24 shrink-0 text-right text-[11.5px] tabular text-ink-faint">
                            {formatPercent(column["Missing Percentage"])} missing
                          </span>
                        </div>
                      ))
                    )}
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="preview">
              <Card>
                <CardHeader>
                  <div>
                    <CardTitle>Row preview</CardTitle>
                    <CardDescription>First {profile.preview?.length ?? 0} rows as stored</CardDescription>
                  </div>
                </CardHeader>
                <CardContent className="pt-4">
                  {profile.preview && profile.previewColumns.length > 0 ? (
                    <div className="overflow-x-auto rounded-lg border border-line">
                      <table className="w-full text-left text-[12.5px]">
                        <thead className="bg-surface-sunken">
                          <tr>
                            {profile.previewColumns.map((column) => (
                              <th
                                key={column}
                                className="whitespace-nowrap px-3 py-2.5 font-medium text-ink-muted"
                              >
                                {column}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {profile.preview.map((row, rowIndex) => (
                            <tr key={rowIndex} className="border-t border-line">
                              {row.map((cell, cellIndex) => (
                                <td
                                  key={cellIndex}
                                  className={cn(
                                    "max-w-[240px] truncate px-3 py-2 text-ink",
                                    typeof cell === "number" ? "mono tabular text-right" : "",
                                  )}
                                >
                                  {cell === null || cell === undefined ? (
                                    <span className="text-ink-faint">null</span>
                                  ) : typeof cell === "boolean" ? (
                                    cell ? "true" : "false"
                                  ) : (
                                    String(cell)
                                  )}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p className="text-[13px] text-ink-muted">No preview available for this file.</p>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="columns">
              <Card>
                <CardHeader>
                  <div>
                    <CardTitle>Schema</CardTitle>
                    <CardDescription>Detected types and cardinality</CardDescription>
                  </div>
                </CardHeader>
                <CardContent className="pt-4">
                  <div className="space-y-2">
                    {profile.columnHealth.map((column) => (
                      <div
                        key={column.Column}
                        className="flex items-center justify-between gap-4 rounded-lg border border-line bg-surface-sunken px-3.5 py-2.5"
                      >
                        <div className="min-w-0">
                          <p className="truncate text-[13px] font-medium text-ink">{column.Column}</p>
                          <p className="mono text-[11px] text-ink-faint">{column.Type}</p>
                        </div>
                        <div className="flex shrink-0 items-center gap-3 text-[11.5px] text-ink-muted">
                          <span className="tabular">{formatNumber(column.Unique)} unique</span>
                          <Badge
                            variant={
                              column["Missing Percentage"] === 0
                                ? "success"
                                : column["Missing Percentage"] > 20
                                  ? "danger"
                                  : "warning"
                            }
                          >
                            {formatPercent(column["Missing Percentage"])} missing
                          </Badge>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="statistics">
              <Card>
                <CardHeader>
                  <div>
                    <CardTitle>Numeric statistics</CardTitle>
                    <CardDescription>Computed from the stored file, never sampled</CardDescription>
                  </div>
                </CardHeader>
                <CardContent className="pt-4">
                  {profile.statistics && profile.statistics.numeric.length > 0 ? (
                    <div className="overflow-x-auto rounded-lg border border-line">
                      <table className="w-full text-left text-[12.5px]">
                        <thead className="bg-surface-sunken text-[11px] uppercase tracking-wider text-ink-faint">
                          <tr>
                            <th className="px-3.5 py-2.5 font-medium">Column</th>
                            <th className="px-3.5 py-2.5 text-right font-medium">Mean</th>
                            <th className="px-3.5 py-2.5 text-right font-medium">Median</th>
                            <th className="px-3.5 py-2.5 text-right font-medium">Std dev</th>
                            <th className="px-3.5 py-2.5 text-right font-medium">Min</th>
                            <th className="px-3.5 py-2.5 text-right font-medium">Max</th>
                          </tr>
                        </thead>
                        <tbody>
                          {profile.statistics.numeric.map((stat) => (
                            <tr key={stat.Column} className="border-t border-line">
                              <td className="px-3.5 py-2.5 font-medium text-ink">{stat.Column}</td>
                              <td className="mono px-3.5 py-2.5 text-right tabular text-ink-muted">
                                {round(stat.Mean)}
                              </td>
                              <td className="mono px-3.5 py-2.5 text-right tabular text-ink-muted">
                                {round(stat.Median)}
                              </td>
                              <td className="mono px-3.5 py-2.5 text-right tabular text-ink-muted">
                                {round(stat["Standard Deviation"])}
                              </td>
                              <td className="mono px-3.5 py-2.5 text-right tabular text-ink-muted">
                                {round(stat.Min)}
                              </td>
                              <td className="mono px-3.5 py-2.5 text-right tabular text-ink-muted">
                                {round(stat.Max)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p className="text-[13px] text-ink-muted">No numeric columns detected.</p>
                  )}

                  {profile.statistics &&
                    Object.entries(profile.statistics.categorical).map(([column, distribution]) => (
                      <div key={column} className="mt-5">
                        <p className="mb-2 text-[11.5px] font-medium uppercase tracking-wider text-ink-faint">
                          {column} distribution
                        </p>
                        <div className="flex flex-wrap gap-2">
                          {distribution.slice(0, 8).map((entry) => (
                            <Badge key={entry.Category} variant="neutral">
                              {entry.Category} · <span className="mono">{entry.Frequency}</span>
                            </Badge>
                          ))}
                        </div>
                      </div>
                    ))}
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </div>

        <div className="space-y-4">
          <Card className="relative overflow-hidden">
            <div
              aria-hidden
              className="pointer-events-none absolute -right-14 -top-14 h-36 w-36 rounded-full opacity-30 blur-3xl"
              style={{ backgroundImage: "var(--gradient-accent)" }}
            />
            <CardHeader>
              <div className="flex items-center gap-2">
                <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-accent/30 bg-accent-soft text-accent">
                  <Sparkles className="h-4 w-4" />
                </span>
                <div>
                  <CardTitle>Analysis</CardTitle>
                  <CardDescription>Unified intelligence pipeline</CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="pt-4">
              {data.isCurrentAnalysis && currentReport ? (
                <div className="space-y-3">
                  <div className="flex items-center gap-2 text-[13px] text-emerald">
                    <CheckCircle2 className="h-4 w-4" />
                    Current analysis loaded
                  </div>
                  <p className="text-[13px] leading-relaxed text-ink-muted">
                    {currentReport.prioritized_findings.length} findings ·{" "}
                    {currentReport.evidence.length} evidence items ·{" "}
                    {currentReport.ai_analysis.insights.length} AI insights
                  </p>
                  <Button variant="secondary" size="sm" className="w-full" onClick={() => navigate("/analytics")}>
                    Open analytics
                    <ArrowRight className="h-3.5 w-3.5" />
                  </Button>
                </div>
              ) : (
                <div className="space-y-3">
                  <p className="text-[13px] leading-relaxed text-ink-muted">
                    {dataset.reportAvailable
                      ? "A TXT report exists for this dataset. Run the unified analysis to refresh charts, evidence and AI interpretation."
                      : "Run the unified analysis to generate metrics, trends, anomalies, prioritized findings and an AI interpretation."}
                  </p>
                  <Button
                    variant="primary"
                    size="sm"
                    className="w-full"
                    onClick={() => void analyze()}
                    loading={analyzing}
                  >
                    <BarChart3 className="h-3.5 w-3.5" />
                    Analyze dataset
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div>
                <CardTitle>File details</CardTitle>
                <CardDescription>Stored locally, never uploaded</CardDescription>
              </div>
            </CardHeader>
            <CardContent className="pt-4">
              <dl className="space-y-2.5 text-[12.5px]">
                <DetailRow label="Filename" value={dataset.fileName} mono />
                <DetailRow label="Size" value={formatBytes(dataset.sizeBytes)} />
                <DetailRow label="Rows" value={formatNumber(dataset.rowCount)} />
                <DetailRow label="Columns" value={formatNumber(dataset.columnCount)} />
                <DetailRow label="Uploaded" value={formatDateTime(dataset.createdAt)} />
                <DetailRow label="SHA-256" value={dataset.sha256.slice(0, 16) + "…"} mono />
              </dl>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-line bg-surface-sunken px-3.5 py-3">
      <p className="text-[11px] font-medium uppercase tracking-wider text-ink-faint">{label}</p>
      <p className="mt-1 text-lg font-semibold tabular text-ink">{value}</p>
    </div>
  );
}

function DetailRow({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-ink-faint">{label}</dt>
      <dd className={cn("truncate text-right text-ink", mono && "mono")}>{value}</dd>
    </div>
  );
}

function round(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const abs = Math.abs(value);
  if (abs >= 1_000_000 || (abs > 0 && abs < 0.01)) return value.toExponential(2);
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(value);
}
