import { useLocation, useNavigate } from "react-router-dom";
import { motion } from "motion/react";
import {
  ChevronDown,
  Database,
  Moon,
  Plus,
  Settings,
  Sun,
} from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { useAsync } from "@/hooks/use-async";
import { api } from "@/lib/api/endpoints";
import { useAppStore, type ThemeSetting } from "@/store/app-store";
import { cn, truncate } from "@/lib/utils";

const PAGE_TITLES: Record<string, string> = {
  "/": "Overview",
  "/datasets": "Datasets",
  "/analytics": "Analytics",
  "/insights": "AI Insights",
  "/reports": "Reports",
  "/settings": "Settings",
};

function pageTitle(pathname: string): string {
  if (PAGE_TITLES[pathname]) return PAGE_TITLES[pathname];
  if (pathname.startsWith("/datasets/")) return "Dataset details";
  return "Overview";
}

function nextTheme(current: ThemeSetting): ThemeSetting {
  return current === "dark" ? "light" : "dark";
}

export function Topbar() {
  const location = useLocation();
  const navigate = useNavigate();
  const title = pageTitle(location.pathname);

  const theme = useAppStore((state) => state.theme);
  const setTheme = useAppStore((state) => state.setTheme);
  const selectedDatasetId = useAppStore((state) => state.selectedDatasetId);
  const setSelectedDatasetId = useAppStore((state) => state.setSelectedDatasetId);
  const datasetsVersion = useAppStore((state) => state.datasetsVersion);
  const profileName = useAppStore((state) => state.profileName);

  const datasets = useAsync(() => api.listDatasets(), [datasetsVersion]);
  const items = datasets.data?.datasets ?? [];
  const resolvedTheme =
    document.documentElement.dataset.theme ?? (theme === "light" ? "light" : "dark");

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-canvas/85 backdrop-blur-xl">
      <div className="flex h-16 items-center gap-4 px-7">
        <div className="flex min-w-0 items-center gap-2.5 text-sm">
          <span className="hidden text-ink-faint sm:inline">VISORA</span>
          <span className="hidden text-ink-faint sm:inline">/</span>
          <motion.span
            key={title}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
            className="truncate font-medium tracking-tight text-ink"
          >
            {title}
          </motion.span>
        </div>

        <div className="ml-auto flex items-center gap-2.5">
          {items.length > 0 && (
            <div className="hidden w-[220px] md:block">
              <Select
                value={selectedDatasetId ?? ""}
                onValueChange={(value) => setSelectedDatasetId(value || null)}
              >
                <SelectTrigger className="h-9" aria-label="Active dataset">
                  <Database className="h-3.5 w-3.5 shrink-0 text-ink-faint" />
                  <SelectValue placeholder="Select dataset">
                    {truncate(
                      items.find((item) => item.id === selectedDatasetId)?.displayName ??
                        "Select dataset",
                      22,
                    )}
                  </SelectValue>
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
          )}

          <Button
            variant="primary"
            size="sm"
            onClick={() => navigate("/datasets?upload=1")}
            className="hidden sm:inline-flex"
          >
            <Plus className="h-3.5 w-3.5" />
            New upload
          </Button>

          <button
            type="button"
            onClick={() => setTheme(nextTheme(theme))}
            aria-label={resolvedTheme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-line text-ink-muted transition-all hover:border-line-strong hover:text-ink"
          >
            {resolvedTheme === "dark" ? (
              <Sun className="h-4 w-4" />
            ) : (
              <Moon className="h-4 w-4" />
            )}
          </button>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                aria-label="Account menu"
                className={cn(
                  "flex h-8 w-8 items-center justify-center rounded-full text-[11.5px] font-semibold text-white gradient-bg",
                  "transition-transform hover:scale-105 focus-visible:outline-none",
                )}
                title={profileName}
              >
                {profileName
                  .split(/\s+/)
                  .filter(Boolean)
                  .slice(0, 2)
                  .map((part) => part[0]?.toUpperCase())
                  .join("") || "VO"}
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-52">
              <DropdownMenuLabel>Local workspace</DropdownMenuLabel>
              <DropdownMenuItem onSelect={() => navigate("/settings")}>
                <Settings className="h-3.5 w-3.5" />
                Settings
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => setTheme(nextTheme(theme))}>
                {resolvedTheme === "dark" ? (
                  <Sun className="h-3.5 w-3.5" />
                ) : (
                  <Moon className="h-3.5 w-3.5" />
                )}
                Switch theme
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem disabled>
                <ChevronDown className="h-3.5 w-3.5" />
                Data stays on this machine
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </header>
  );
}
