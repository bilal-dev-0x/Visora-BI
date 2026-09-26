import { NavLink } from "react-router-dom";
import { motion } from "motion/react";
import {
  BarChart3,
  ChevronLeft,
  ChevronRight,
  Database,
  FileText,
  LayoutDashboard,
  Settings,
  Sparkles,
} from "lucide-react";
import { BrandLockup } from "@/components/brand/logo";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Skeleton } from "@/components/ui/skeleton";
import { useAsync } from "@/hooks/use-async";
import { api } from "@/lib/api/endpoints";
import { useAppStore } from "@/store/app-store";
import { cn, truncate } from "@/lib/utils";

interface NavItemDefinition {
  to: string;
  label: string;
  icon: typeof LayoutDashboard;
  end?: boolean;
}

const PRIMARY_NAV: NavItemDefinition[] = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/datasets", label: "Datasets", icon: Database },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
  { to: "/insights", label: "AI Insights", icon: Sparkles },
  { to: "/reports", label: "Reports", icon: FileText },
];

const SECONDARY_NAV: NavItemDefinition[] = [
  { to: "/settings", label: "Settings", icon: Settings },
];

function NavItem({
  item,
  collapsed,
}: {
  item: NavItemDefinition;
  collapsed: boolean;
}) {
  const Icon = item.icon;
  const link = (
    <NavLink
      to={item.to}
      end={item.end}
      className="relative"
    >
      {({ isActive }) => (
        <span
          className={cn(
            "flex h-9 items-center gap-3 rounded-lg px-2.5 text-[13.5px] font-medium transition-colors duration-200",
            collapsed ? "justify-center px-0" : "",
            isActive
              ? "bg-accent-soft text-ink"
              : "text-ink-muted hover:bg-surface-hover hover:text-ink",
          )}
        >
          {isActive && (
            <motion.span
              layoutId="nav-active-indicator"
              className="absolute -left-2.5 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-full gradient-bg"
              transition={{ type: "spring", stiffness: 460, damping: 36 }}
            />
          )}
          <Icon className="h-[17px] w-[17px] shrink-0" strokeWidth={1.9} />
          {!collapsed && <span className="truncate">{item.label}</span>}
        </span>
      )}
    </NavLink>
  );

  if (!collapsed) return link;

  return (
    <Tooltip delayDuration={120}>
      <TooltipTrigger asChild>{link}</TooltipTrigger>
      <TooltipContent side="right">{item.label}</TooltipContent>
    </Tooltip>
  );
}

export function Sidebar() {
  const collapsed = useAppStore((state) => state.sidebarCollapsed);
  const toggle = useAppStore((state) => state.toggleSidebar);
  const datasetsVersion = useAppStore((state) => state.datasetsVersion);

  const health = useAsync(() => api.health(), []);
  const datasets = useAsync(() => api.listDatasets(), [datasetsVersion]);
  const recent = (datasets.data?.datasets ?? []).slice(0, 4);

  return (
    <motion.aside
      className="sticky top-0 z-40 flex h-screen shrink-0 flex-col border-r border-line bg-sidebar"
      initial={false}
      animate={{ width: collapsed ? 74 : 240 }}
      transition={{ type: "spring", stiffness: 300, damping: 34 }}
    >
      <div
        className={cn(
          "flex h-16 shrink-0 items-center border-b border-line",
          collapsed ? "justify-center px-0" : "px-4",
        )}
      >
        <BrandLockup compact={collapsed} />
      </div>

      <nav className="flex-1 overflow-y-auto overflow-x-hidden px-3 py-4">
        <p
          className={cn(
            "mb-2 px-2.5 text-[10.5px] font-semibold uppercase tracking-[0.14em] text-ink-faint transition-opacity",
            collapsed && "opacity-0",
          )}
        >
          Workspace
        </p>
        <div className="space-y-1">
          {PRIMARY_NAV.map((item) => (
            <NavItem key={item.to} item={item} collapsed={collapsed} />
          ))}
        </div>

        <div className="mt-6">
          <p
            className={cn(
              "mb-2 px-2.5 text-[10.5px] font-semibold uppercase tracking-[0.14em] text-ink-faint transition-opacity",
              collapsed && "opacity-0",
            )}
          >
            Recent
          </p>
          {collapsed ? (
            <div className="space-y-1.5 px-1">
              {recent.map((dataset) => (
                <NavLink key={dataset.id} to={`/datasets/${dataset.id}`} className="block">
                  <span
                    className={cn(
                      "block h-7 w-full rounded-md border border-line bg-surface-sunken",
                      dataset.status === "ready" ? "" : "opacity-60",
                    )}
                  />
                </NavLink>
              ))}
              {datasets.loading && (
                <Skeleton className="h-7 w-full rounded-md" />
              )}
            </div>
          ) : (
            <div className="space-y-0.5">
              {datasets.loading && (
                <div className="space-y-1.5 px-1">
                  <Skeleton className="h-7 w-full rounded-md" />
                  <Skeleton className="h-7 w-4/5 rounded-md" />
                </div>
              )}
              {recent.map((dataset) => (
                <NavLink
                  key={dataset.id}
                  to={`/datasets/${dataset.id}`}
                  className="flex h-7 items-center gap-2 rounded-md px-2.5 text-xs text-ink-muted transition-colors hover:bg-surface-hover hover:text-ink"
                >
                  <span
                    className={cn(
                      "h-1.5 w-1.5 shrink-0 rounded-full",
                      dataset.status === "ready" ? "bg-emerald" : "bg-amber",
                    )}
                  />
                  <span className="truncate">{truncate(dataset.displayName, 22)}</span>
                </NavLink>
              ))}
              {!datasets.loading && recent.length === 0 && (
                <p className="px-2.5 text-[11.5px] leading-relaxed text-ink-faint">
                  No datasets yet.
                </p>
              )}
            </div>
          )}
        </div>

        <div className="mt-6 space-y-1">
          {SECONDARY_NAV.map((item) => (
            <NavItem key={item.to} item={item} collapsed={collapsed} />
          ))}
        </div>
      </nav>

      <div className="shrink-0 border-t border-line p-3">
        {!collapsed ? (
          <div className="mb-2.5 rounded-lg border border-line bg-surface-sunken px-3 py-2.5">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-medium uppercase tracking-wider text-ink-faint">
                System
              </span>
              <span className="flex items-center gap-1.5 text-[11px] text-emerald">
                <span className="relative flex h-1.5 w-1.5">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald opacity-60" />
                  <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald" />
                </span>
                {health.error ? "Offline" : "Online"}
              </span>
            </div>
            <div className="mt-2 space-y-1 text-[11.5px] text-ink-muted">
              <div className="flex items-center justify-between">
                <span>Datasets</span>
                <span className="mono tabular">{health.data?.datasets ?? "—"}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>AI engine</span>
                <span className="capitalize">
                  {health.data ? health.data.ai.mode.replace("_", " ") : "—"}
                </span>
              </div>
            </div>
          </div>
        ) : (
          <div className="mb-2.5 flex justify-center">
            <span
              className={cn(
                "h-2 w-2 rounded-full",
                health.error ? "bg-rose" : health.loading ? "bg-amber animate-pulse-soft" : "bg-emerald",
              )}
              title={health.error ? "API offline" : "API online"}
            />
          </div>
        )}

        <button
          type="button"
          onClick={toggle}
          className={cn(
            "flex h-8 w-full items-center gap-2 rounded-lg px-2.5 text-xs text-ink-faint transition-colors hover:bg-surface-hover hover:text-ink",
            collapsed && "justify-center px-0",
          )}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? (
            <ChevronRight className="h-4 w-4" />
          ) : (
            <>
              <ChevronLeft className="h-4 w-4" />
              <span>Collapse</span>
            </>
          )}
        </button>
      </div>
    </motion.aside>
  );
}
