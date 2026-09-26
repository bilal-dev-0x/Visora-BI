import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowRight,
  Download,
  FileText,
  History,
  RefreshCw,
  Sparkles,
  Trash2,
} from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { ConfirmationDialog } from "@/components/shared/confirmation-dialog";
import { EmptyState, ErrorState, LoadingState } from "@/components/shared/async-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Reveal, Stagger, StaggerItem } from "@/components/motion/motion";
import { useAsync } from "@/hooks/use-async";
import { api } from "@/lib/api/endpoints";
import { notifyError, notifySuccess } from "@/lib/notify";
import { useAppStore } from "@/store/app-store";
import { formatBytes, formatDateTime, formatRelative, truncate } from "@/lib/utils";

export function ReportsPage() {
  const navigate = useNavigate();
  const datasetsVersion = useAppStore((state) => state.datasetsVersion);
  const bump = useAppStore((state) => state.bumpDatasetsVersion);
  const clearCache = useAppStore((state) => state.clearCache);
  const setSelectedDatasetId = useAppStore((state) => state.setSelectedDatasetId);

  const { data, loading, error, reload } = useAsync(
    () => api.listReports(),
    [datasetsVersion],
  );
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  const download = useCallback(
    async (datasetId: string, fallback: string) => {
      setDownloadingId(datasetId);
      try {
        await api.downloadReport(datasetId, fallback);
        notifySuccess("Report downloaded");
      } catch (caught) {
        notifyError(caught);
      } finally {
        setDownloadingId(null);
      }
    },
    [],
  );

  const clearHistory = useCallback(async () => {
    try {
      const result = await api.clearHistory();
      clearCache();
      bump();
      setSelectedDatasetId(null);
      notifySuccess(
        "History cleared",
        `${result.deleted_datasets} dataset(s) and ${result.deleted_reports} report(s) removed.`,
      );
      reload();
    } catch (caught) {
      notifyError(caught);
    }
  }, [bump, clearCache, reload, setSelectedDatasetId]);

  if (loading && !data) return <LoadingState variant="table" rows={5} />;
  if (error && !data) return <ErrorState error={error} onRetry={reload} />;

  const reports = data?.reports ?? [];
  const current = data?.current ?? null;
  const isEmpty = reports.length === 0 && !current;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Reports"
        description="Analysis outputs you can download, audit and share — generated from your data only."
        actions={
          <>
            <Button variant="secondary" size="md" onClick={reload} loading={loading}>
              <RefreshCw className="h-3.5 w-3.5" />
              Refresh
            </Button>
            {!isEmpty && (
              <ConfirmationDialog
                title="Clear all history?"
                description="Every stored dataset, analytical table and generated report will be permanently removed. This can't be undone."
                confirmLabel="Clear everything"
                onConfirm={clearHistory}
                trigger={
                  <Button variant="danger" size="md">
                    <Trash2 className="h-3.5 w-3.5" />
                    Clear history
                  </Button>
                }
              />
            )}
          </>
        }
      />

      {isEmpty ? (
        <EmptyState
          icon={
            <div className="flex h-12 w-12 items-center justify-center rounded-xl border border-line-strong bg-surface-raised text-ink-muted">
              <FileText className="h-5 w-5" />
            </div>
          }
          title="No reports yet"
          description="Run an analysis on any dataset and VISORA will write a downloadable text report plus a unified JSON snapshot powering this dashboard."
          action={
            <Button variant="primary" onClick={() => navigate("/analytics")}>
              Go to Analytics
              <ArrowRight className="h-4 w-4" />
            </Button>
          }
          secondaryAction={
            <Button variant="ghost" onClick={() => navigate("/datasets?upload=1")}>
              Upload a dataset
            </Button>
          }
        />
      ) : (
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="space-y-4 lg:col-span-2">
            <Stagger className="space-y-3" stagger={0.06}>
              {reports.map((report) => (
                <StaggerItem key={report.id}>
                  <div className="panel group flex items-center gap-4 rounded-xl px-4 py-3.5 transition-all hover:border-line-strong">
                    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-line bg-surface-sunken text-ink-faint transition-colors group-hover:text-accent">
                      <FileText className="h-4 w-4" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="truncate text-[14px] font-medium text-ink">
                          {truncate(report.displayName, 34)}
                        </p>
                        <Badge variant="neutral" className="uppercase tracking-wider">
                          {report.kind === "text" ? "TXT" : "JSON"}
                        </Badge>
                      </div>
                      <p className="mono mt-0.5 truncate text-[11.5px] text-ink-faint">
                        {report.fileName} · {formatBytes(report.sizeBytes)} ·{" "}
                        {report.generatedAt ? formatRelative(report.generatedAt) : "—"}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      {report.kind === "text" && report.datasetId ? (
                        <Button
                          variant="secondary"
                          size="sm"
                          loading={downloadingId === report.datasetId}
                          onClick={() =>
                            void download(report.datasetId as string, report.fileName)
                          }
                        >
                          <Download className="h-3.5 w-3.5" />
                          Download
                        </Button>
                      ) : (
                        <Button variant="ghost" size="sm" onClick={() => navigate("/analytics")}>
                          Open analysis
                          <ArrowRight className="h-3.5 w-3.5" />
                        </Button>
                      )}
                    </div>
                  </div>
                </StaggerItem>
              ))}
            </Stagger>
          </div>

          <div className="space-y-4">
            <Reveal delay={0.1}>
              <Card className="relative overflow-hidden">
                <div
                  aria-hidden
                  className="pointer-events-none absolute -right-16 -top-16 h-40 w-40 rounded-full opacity-30 blur-3xl"
                  style={{ backgroundImage: "var(--gradient-accent)" }}
                />
                <CardHeader>
                  <div className="flex items-center gap-2">
                    <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-accent/30 bg-accent-soft text-accent">
                      <Sparkles className="h-4 w-4" />
                    </span>
                    <div>
                      <CardTitle>Unified snapshot</CardTitle>
                      <CardDescription>
                        {current ? "Current report on disk" : "No snapshot yet"}
                      </CardDescription>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="pt-4">
                  {current ? (
                    <div className="space-y-3">
                      <dl className="space-y-2 text-[12.5px]">
                        <div className="flex justify-between gap-3">
                          <dt className="text-ink-faint">File</dt>
                          <dd className="mono truncate text-ink">{current.fileName}</dd>
                        </div>
                        <div className="flex justify-between gap-3">
                          <dt className="text-ink-faint">Size</dt>
                          <dd className="tabular text-ink">{formatBytes(current.sizeBytes)}</dd>
                        </div>
                        <div className="flex justify-between gap-3">
                          <dt className="text-ink-faint">Generated</dt>
                          <dd className="text-ink">
                            {current.generatedAt ? formatDateTime(current.generatedAt) : "—"}
                          </dd>
                        </div>
                      </dl>
                      <Button
                        variant="secondary"
                        size="sm"
                        className="w-full"
                        onClick={() => navigate("/analytics")}
                      >
                        View in analytics
                        <ArrowRight className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  ) : (
                    <p className="text-[13px] leading-relaxed text-ink-muted">
                      The unified snapshot is written whenever an analysis runs. It powers the
                      overview, insights and analytics views.
                    </p>
                  )}
                </CardContent>
              </Card>
            </Reveal>

            <Reveal delay={0.16}>
              <Card>
                <CardHeader>
                  <div className="flex items-center gap-2">
                    <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-line-strong bg-surface-sunken text-ink-muted">
                      <History className="h-4 w-4" />
                    </span>
                    <div>
                      <CardTitle>Retention</CardTitle>
                      <CardDescription>Local-first storage</CardDescription>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="pt-4">
                  <p className="text-[13px] leading-relaxed text-ink-muted">
                    Reports live in your project's <span className="mono text-ink">reports/</span>{" "}
                    directory next to the SQLite registry. Clearing history removes reports and
                    datasets together — no orphans, no partial deletes.
                  </p>
                  {!isEmpty && (
                    <ConfirmationDialog
                      title="Clear all history?"
                      description="Every stored dataset, analytical table and generated report will be permanently removed. This can't be undone."
                      confirmLabel="Clear everything"
                      onConfirm={clearHistory}
                      trigger={
                        <Button variant="danger" size="sm" className="mt-3 w-full">
                          <Trash2 className="h-3.5 w-3.5" />
                          Clear history
                        </Button>
                      }
                    />
                  )}
                </CardContent>
              </Card>
            </Reveal>
          </div>
        </div>
      )}
    </div>
  );
}
