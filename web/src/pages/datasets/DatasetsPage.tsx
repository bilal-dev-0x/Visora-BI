import { useCallback, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import {
  BarChart3,
  Database,
  FileText,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { StatusBadge } from "@/components/shared/kpi-card";
import { ConfirmationDialog } from "@/components/shared/confirmation-dialog";
import { EmptyState, ErrorState, LoadingState } from "@/components/shared/async-state";
import { UploadDropzone } from "@/components/upload/upload-dropzone";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useAsync } from "@/hooks/use-async";
import { api } from "@/lib/api/endpoints";
import { notifyError, notifySuccess } from "@/lib/notify";
import { useAppStore } from "@/store/app-store";
import { cn, formatBytes, formatNumber, formatRelative } from "@/lib/utils";

export function DatasetsPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const datasetsVersion = useAppStore((state) => state.datasetsVersion);
  const bump = useAppStore((state) => state.bumpDatasetsVersion);
  const setSelectedDatasetId = useAppStore((state) => state.setSelectedDatasetId);
  const invalidateReport = useAppStore((state) => state.invalidateReport);
  const clearCache = useAppStore((state) => state.clearCache);
  const cacheReport = useAppStore((state) => state.cacheReport);

  const health = useAsync(() => api.health(), []);
  const {
    data,
    loading,
    error,
    reload,
  } = useAsync(() => api.listDatasets(), [datasetsVersion]);

  const [analyzingId, setAnalyzingId] = useState<string | null>(null);
  const datasets = data?.datasets ?? [];
  const maxBytes = health.data?.uploadLimitBytes ?? 150 * 1024 * 1024;

  const handleUploaded = useCallback(
    (dataset: { id: string; displayName: string }, warning: string | null) => {
      setSelectedDatasetId(dataset.id);
      bump();
      if (warning) {
        toast.warning("Saved, but needs attention", { description: warning });
      } else {
        notifySuccess("Dataset uploaded", `${dataset.displayName} is ready to analyze.`);
      }
      if (searchParams.has("upload")) setSearchParams({}, { replace: true });
      navigate(`/datasets/${dataset.id}`);
    },
    [bump, navigate, searchParams, setSelectedDatasetId, setSearchParams],
  );

  const handleAnalyze = useCallback(
    async (id: string) => {
      setAnalyzingId(id);
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
        notifySuccess("Analysis ready", "Charts, evidence and insights are up to date.");
        navigate("/analytics");
      } catch (caught) {
        notifyError(caught);
      } finally {
        setAnalyzingId(null);
      }
    },
    [bump, cacheReport, invalidateReport, navigate, setSelectedDatasetId],
  );

  const handleClearHistory = useCallback(async () => {
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

  return (
    <div className="space-y-6">
      <PageHeader
        title="Datasets"
        description="Upload, profile and manage every file this workspace has analyzed."
        actions={
          <>
            <Button variant="secondary" size="md" onClick={reload} loading={loading && !!data}>
              <RefreshCw className="h-3.5 w-3.5" />
              Refresh
            </Button>
            {datasets.length > 0 && (
              <ConfirmationDialog
                title="Clear all history?"
                description="Every stored dataset, analytical table and generated report will be permanently removed. This can't be undone."
                confirmLabel="Clear everything"
                onConfirm={handleClearHistory}
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

      <div id="upload">
        <UploadDropzone maxBytes={maxBytes} onUploaded={handleUploaded} />
      </div>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold tracking-tight text-ink">
            Dataset history
            <span className="ml-2 text-[12.5px] font-normal text-ink-faint">
              {loading && !data ? "loading…" : `${datasets.length} total`}
            </span>
          </h2>
        </div>

        {loading && !data ? (
          <LoadingState variant="table" rows={4} />
        ) : error ? (
          <ErrorState error={error} onRetry={reload} />
        ) : datasets.length === 0 ? (
          <EmptyState
            compact
            icon={
              <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-line-strong bg-surface-raised text-ink-muted">
                <Database className="h-5 w-5" />
              </div>
            }
            title="No datasets yet"
            description="Drop a file above to create your first dataset. VISORA will profile it, ingest it and make it analyzable in seconds."
          />
        ) : (
          <div className="panel overflow-hidden rounded-xl">
            <table className="w-full text-left text-[13px]">
              <thead>
                <tr className="border-b border-line text-[11px] uppercase tracking-wider text-ink-faint">
                  <th className="px-5 py-3 font-medium">Dataset</th>
                  <th className="px-4 py-3 font-medium">Rows</th>
                  <th className="px-4 py-3 font-medium">Columns</th>
                  <th className="px-4 py-3 font-medium">Size</th>
                  <th className="px-4 py-3 font-medium">Uploaded</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-5 py-3 text-right font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {datasets.map((dataset) => (
                  <tr
                    key={dataset.id}
                    onClick={() => navigate(`/datasets/${dataset.id}`)}
                    className="group cursor-pointer border-b border-line last:border-0 transition-colors hover:bg-surface-hover"
                  >
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-3">
                        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-line bg-surface-sunken text-ink-faint">
                          <FileText className="h-3.5 w-3.5" />
                        </span>
                        <div className="min-w-0">
                          <p className="truncate font-medium text-ink">{dataset.displayName}</p>
                          <p className="mono truncate text-[11px] text-ink-faint">
                            {dataset.fileName}
                          </p>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3.5 tabular text-ink-muted">
                      {formatNumber(dataset.rowCount)}
                    </td>
                    <td className="px-4 py-3.5 tabular text-ink-muted">
                      {formatNumber(dataset.columnCount)}
                    </td>
                    <td className="px-4 py-3.5 text-ink-muted">{formatBytes(dataset.sizeBytes)}</td>
                    <td className="px-4 py-3.5 text-ink-muted">
                      {formatRelative(dataset.createdAt)}
                    </td>
                    <td className="px-4 py-3.5">
                      <StatusBadge status={dataset.status} />
                    </td>
                    <td className="px-5 py-3.5">
                      <div
                        className="flex items-center justify-end gap-1.5"
                        onClick={(event) => event.stopPropagation()}
                      >
                        {dataset.reportAvailable && (
                          <Badge variant="neutral" className="hidden lg:inline-flex">
                            <FileText className="h-3 w-3" />
                            report
                          </Badge>
                        )}
                        <Button
                          variant="soft"
                          size="sm"
                          loading={analyzingId === dataset.id}
                          disabled={dataset.status !== "ready" || analyzingId !== null}
                          onClick={() => void handleAnalyze(dataset.id)}
                        >
                          <BarChart3 className="h-3.5 w-3.5" />
                          Analyze
                        </Button>
                        <ConfirmationDialog
                          title={`Delete ${dataset.displayName}?`}
                          description="The stored file, its analytical table and its report will be removed. Datasets that share this report are unaffected."
                          confirmLabel="Delete dataset"
                          onConfirm={async () => {
                            try {
                              await api.deleteDataset(dataset.id);
                              invalidateReport(dataset.id);
                              bump();
                              notifySuccess("Dataset deleted", `${dataset.displayName} was removed.`);
                              reload();
                            } catch (caught) {
                              notifyError(caught);
                            }
                          }}
                          trigger={
                            <Button
                              variant="ghost"
                              size="icon-sm"
                              aria-label={`Delete ${dataset.displayName}`}
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          }
                        />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <p className={cn("text-[12px] text-ink-faint", datasets.length === 0 && "hidden")}>
        Need a sample? Drop any CSV export from your POS, CRM or ad platform — VISORA detects
        dates, measures and dimensions automatically.
      </p>
    </div>
  );
}
