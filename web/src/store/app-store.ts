import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { UnifiedReport } from "@/lib/api/types";

export type ThemeSetting = "dark" | "light" | "system";

interface Preferences {
  theme: ThemeSetting;
  sidebarCollapsed: boolean;
  selectedDatasetId: string | null;
  /** Sidebar "compact list" density for dataset history. */
  denseLists: boolean;
  /** Local display name used for the account avatar (no auth backend). */
  profileName: string;
}

interface AppState extends Preferences {
  /** In-memory unified reports keyed by dataset id (never persisted). */
  reports: Record<string, UnifiedReport>;
  reportLoading: Record<string, boolean>;
  /** Bumped after upload/delete/clear so every dataset list reloads. */
  datasetsVersion: number;

  setTheme: (theme: ThemeSetting) => void;
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  setSelectedDatasetId: (id: string | null) => void;
  setDenseLists: (dense: boolean) => void;
  setProfileName: (name: string) => void;
  cacheReport: (datasetId: string, report: UnifiedReport) => void;
  setReportLoading: (datasetId: string, loading: boolean) => void;
  invalidateReport: (datasetId: string) => void;
  bumpDatasetsVersion: () => void;
  clearCache: () => void;
}

export const applyTheme = (theme: ThemeSetting) => {
  const root = document.documentElement;
  const resolved =
    theme === "system"
      ? window.matchMedia("(prefers-color-scheme: light)").matches
        ? "light"
        : "dark"
      : theme;
  root.dataset.theme = resolved;
  root.classList.toggle("dark", resolved === "dark");
};

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      theme: "dark",
      sidebarCollapsed: false,
      selectedDatasetId: null,
      denseLists: false,
      profileName: "Visora Owner",
      reports: {},
      reportLoading: {},
      datasetsVersion: 0,

      setTheme: (theme) => {
        applyTheme(theme);
        set({ theme });
      },
      toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
      setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
      setSelectedDatasetId: (selectedDatasetId) => set({ selectedDatasetId }),
      setDenseLists: (denseLists) => set({ denseLists }),
      setProfileName: (profileName) => set({ profileName: profileName || "Visora Owner" }),
      cacheReport: (datasetId, report) =>
        set((state) => ({ reports: { ...state.reports, [datasetId]: report } })),
      setReportLoading: (datasetId, loading) =>
        set((state) => ({ reportLoading: { ...state.reportLoading, [datasetId]: loading } })),
      invalidateReport: (datasetId) =>
        set((state) => {
          const reports = { ...state.reports };
          delete reports[datasetId];
          return { reports };
        }),
      bumpDatasetsVersion: () =>
        set((state) => ({ datasetsVersion: state.datasetsVersion + 1 })),
      clearCache: () => set({ reports: {}, reportLoading: {} }),
    }),
    {
      name: "visora-preferences",
      partialize: (state) => ({
        theme: state.theme,
        sidebarCollapsed: state.sidebarCollapsed,
        selectedDatasetId: state.selectedDatasetId,
        denseLists: state.denseLists,
        profileName: state.profileName,
      }),
      onRehydrateStorage: () => (state) => {
        if (state) applyTheme(state.theme);
        else applyTheme("dark");
      },
    },
  ),
);

export const getReportForDataset = (datasetId: string | null): UnifiedReport | null => {
  if (!datasetId) return null;
  return useAppStore.getState().reports[datasetId] ?? null;
};
