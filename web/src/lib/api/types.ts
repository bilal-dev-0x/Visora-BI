/* Shared API contract types.
 *
 * These mirror the JSON produced by api/serializers.py — the Python
 * backend stays the single source of truth for every value. */

export type DatasetStatus = "ready" | "needs_attention";
export type Priority = "critical" | "high" | "medium" | "low";

export interface DatasetSummary {
  id: string;
  fileName: string;
  displayName: string;
  rowCount: number | null;
  columnCount: number | null;
  createdAt: string;
  sizeBytes: number | null;
  sha256: string;
  status: DatasetStatus;
  reportAvailable: boolean;
}

export interface ColumnHealth {
  Column: string;
  Missing: number;
  Unique: number;
  Type: string;
  "Missing Percentage": number;
}

export interface NumericStat {
  Column: string;
  Mean: number | null;
  Median: number | null;
  "Standard Deviation": number | null;
  Min: number | null;
  Max: number | null;
}

export interface CategoricalDistribution {
  Category: string;
  Frequency: number;
}

export interface DatasetQuality {
  missingValues: number;
  missingColumns: string[];
  duplicateRows: number;
  emptyRows: number;
}

export interface DatasetStatistics {
  numeric: NumericStat[];
  categorical: Record<string, CategoricalDistribution[]>;
  dateColumns: string[];
  categoricalColumns: string[];
}

export interface DatasetProfile {
  available: boolean;
  reason: string | null;
  detail?: string;
  previewColumns: string[];
  preview: (string | number | boolean | null)[][] | null;
  quality: DatasetQuality | null;
  columnHealth: ColumnHealth[];
  statistics: DatasetStatistics | null;
}

export interface DatasetDetail {
  dataset: DatasetSummary;
  profile: DatasetProfile;
  status: DatasetStatus;
  isCurrentAnalysis: boolean;
  currentReport: UnifiedReport | null;
}

export interface EvidenceItem {
  id: string;
  type: string;
  title: string;
  value: number | null;
  source: string;
  period: string | null;
  column: string | null;
  date_column: string | null;
}

export interface Finding extends EvidenceItem {
  priority: Priority;
}

export interface AiInsight {
  id: string;
  title: string;
  type: string;
  priority: Priority;
  explanation: string;
  evidence: EvidenceItem[];
}

export interface AiAnalysis {
  available: boolean;
  summary: string;
  insights: AiInsight[];
  risks: string[];
  opportunities: string[];
  source: "ai" | "local_fallback" | string;
  provider_used: string | null;
  ai_skipped_reason: string | null;
}

export interface MetricEntry {
  sum: number;
  average: number;
  min: number;
  max: number;
  count: number;
}

export interface GrowthPoint {
  period: string;
  value: number;
  growth_percent: number | null;
  growth_reason: string | null;
  period_gap_months: number | null;
}

export interface PeriodComparison {
  available: boolean;
  reason: string | null;
  previous_period: string | null;
  current_period: string | null;
  previous_value: number | null;
  current_value: number | null;
  change: number | null;
  change_percent: number | null;
}

export interface AnomalyRow {
  row_id: number;
  metric: string;
  value: number;
  baseline: number;
  z_score: number;
  deviation: number;
  context: Record<string, unknown>;
  reason: string;
}

export interface CapabilitySection<T> {
  available: boolean;
  data?: T | null;
  reason?: string | null;
}

export interface SchemaInfo {
  columns: string[];
  numeric_columns: string[];
  categorical_columns: string[];
  date_columns: string[];
  candidate_measures: string[];
  candidate_dimensions: string[];
}

export interface TrendsData {
  date_column: string;
  measure_column: string;
  monthly: { period: string; value: number }[];
  growth: GrowthPoint[];
  moving_average: { period: string; value: number; moving_average: number | null }[];
  period_comparison: PeriodComparison;
}

export interface ContributionData {
  dimension: string;
  measure: string;
  total_categories: number;
  rows_truncated: boolean;
  truncation_reason: string | null;
  breakdown: { category: string; value: number; percent: number; rank: number }[];
}

export interface UnifiedReport {
  status: "success" | "error" | string;
  error?: string | null;
  generated_at?: string;
  dataset: {
    dataset_id: string;
    original_filename: string;
    table_name?: string;
    row_count: number | null;
    column_count: number | null;
  };
  schema: SchemaInfo;
  data_quality: {
    total_missing_values: number;
    columns_with_missing_values: string[];
    duplicate_rows: number;
    completely_empty_rows: number;
    column_health: ColumnHealth[];
  };
  numeric_statistics: NumericStat[];
  capabilities: Record<string, CapabilitySection<unknown>>;
  metrics: CapabilitySection<Record<string, MetricEntry>>;
  trends: CapabilitySection<TrendsData>;
  contribution: CapabilitySection<ContributionData>;
  anomalies: CapabilitySection<Record<string, AnomalyRow[]>>;
  evidence: EvidenceItem[];
  prioritized_findings: Finding[];
  ai_analysis: AiAnalysis;
}

export interface UploadResponse {
  dataset: DatasetSummary;
  warning: string | null;
}

export interface DeleteResponse {
  deleted: boolean;
  dataset_id: string;
  removed_reports: number;
}

export interface ClearHistoryResponse {
  deleted_datasets: number;
  deleted_reports: number;
}

export interface HealthResponse {
  status: string;
  version: string;
  time: string;
  datasets: number;
  reports: number;
  currentReport: boolean;
  uploadLimitBytes: number;
  uploadLimitMb: number;
  ai: {
    mode: "local_fallback" | "provider_chain";
    configuredProviders: number;
    totalSlots: number;
  };
}

export interface KpiCard {
  id: string;
  label: string;
  value: number | null;
  format: "int" | "percent" | "compact";
  tone: "neutral" | "positive" | "warning" | "critical";
}

export interface OverviewResponse {
  datasets: {
    total: number;
    ready: number;
    totalRows: number;
    recent: DatasetSummary[];
  };
  kpis: KpiCard[];
  trend: {
    datasetId: string | null;
    measure: string | null;
    dateColumn: string | null;
    series: { period: string; value: number | null }[];
    available: boolean;
  };
  contribution: {
    dimension?: string | null;
    measure?: string | null;
    series: { label: string; value: number | null; percent?: number | null }[];
    available: boolean;
  };
  anomalies: { count: number; available: boolean };
  findings: { total: number; critical: number; items: Finding[] };
  insights: { summary: string | null; source: string | null; count: number };
  reports: { reports: ReportRecord[]; current: ReportRecord | null };
  generatedAt: string | null;
  available: boolean;
  reason: string | null;
}

export interface ReportRecord {
  id: string;
  datasetId: string | null;
  fileName: string;
  displayName: string;
  kind: "text" | "unified";
  sizeBytes: number | null;
  generatedAt: string | null;
  downloadUrl: string | null;
}

export interface ReportsResponse {
  reports: ReportRecord[];
  current: ReportRecord | null;
}

export interface InsightsResponse {
  available: boolean;
  reason: string | null;
  dataset: { dataset_id: string; original_filename: string } | null;
  generatedAt: string | null;
  summary: string | null;
  source: string | null;
  providerUsed: string | null;
  skippedReason: string | null;
  attempts: unknown[];
  insights: AiInsight[];
  risks: string[];
  opportunities: string[];
  findings: Finding[];
  evidence: EvidenceItem[];
  analysisStatus: string | null;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    detail?: unknown;
  };
}
