import { del, download, get, post, upload, type UploadOptions } from "./client";
import type {
  ClearHistoryResponse,
  DatasetDetail,
  DeleteResponse,
  HealthResponse,
  InsightsResponse,
  OverviewResponse,
  ReportsResponse,
  UnifiedReport,
  DatasetSummary,
  UploadResponse,
} from "./types";

export const api = {
  health: () => get<HealthResponse>("/health"),
  overview: () => get<OverviewResponse>("/overview"),

  listDatasets: () => get<{ datasets: DatasetSummary[] }>("/datasets"),
  getDataset: (id: string) => get<DatasetDetail>(`/datasets/${id}`),
  uploadDataset: (file: File, options?: UploadOptions) =>
    upload<UploadResponse>("/datasets", file, options),
  analyzeDataset: (id: string) => post<{ report: UnifiedReport }>(`/datasets/${id}/analyze`),
  deleteDataset: (id: string) => del<DeleteResponse>(`/datasets/${id}`),

  listReports: () => get<ReportsResponse>("/reports"),
  currentReport: () => get<UnifiedReport>("/reports/current"),
  downloadReport: (datasetId: string, fallbackName: string) =>
    download(`/reports/${datasetId}/text`, fallbackName),
  clearHistory: () => post<ClearHistoryResponse>("/history/clear"),

  insights: () => get<InsightsResponse>("/insights"),
};
