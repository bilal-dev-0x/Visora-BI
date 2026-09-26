import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { AnimatedNumber } from "@/components/motion/motion";
import { cn } from "@/lib/utils";
import type { Priority } from "@/lib/api/types";

type Tone = "neutral" | "positive" | "warning" | "critical";

const toneClasses: Record<Tone, string> = {
  neutral: "text-ink",
  positive: "text-emerald",
  warning: "text-amber",
  critical: "text-rose",
};

export function KpiCard({
  label,
  value,
  format = "int",
  tone = "neutral",
  hint,
  icon,
  delay = 0,
}: {
  label: string;
  value: number | null;
  format?: "int" | "percent" | "compact";
  tone?: Tone;
  hint?: string;
  icon?: ReactNode;
  delay?: number;
}) {
  const displayValue =
    value === null || Number.isNaN(value) ? "—" : undefined;

  return (
    <div
      className="panel group relative overflow-hidden rounded-xl p-4 transition-all duration-300 hover:-translate-y-0.5 hover:border-line-strong"
      style={{ animation: `rise-in 0.5s cubic-bezier(0.22,1,0.36,1) ${delay}s both` }}
    >
      <div
        aria-hidden
        className="absolute inset-x-0 top-0 h-px opacity-0 transition-opacity duration-300 group-hover:opacity-100"
        style={{ backgroundImage: "var(--gradient-accent)" }}
      />
      <div className="flex items-start justify-between gap-3">
        <p className="text-[11.5px] font-medium uppercase tracking-[0.09em] text-ink-faint">
          {label}
        </p>
        {icon && <span className="text-ink-faint transition-colors group-hover:text-ink-muted">{icon}</span>}
      </div>
      <div className={cn("mt-2.5 text-[27px] font-semibold leading-none tracking-tight", toneClasses[tone])}>
        {displayValue ?? (
          <AnimatedNumber
            value={value as number}
            format={format}
            className={toneClasses[tone]}
          />
        )}
      </div>
      {hint && <p className="mt-2 text-xs text-ink-faint">{hint}</p>}
    </div>
  );
}

export function StatTile({
  label,
  value,
  sublabel,
  className,
}: {
  label: string;
  value: ReactNode;
  sublabel?: string;
  className?: string;
}) {
  return (
    <div className={cn("rounded-lg border border-line bg-surface-sunken px-3.5 py-3", className)}>
      <p className="text-[11px] font-medium uppercase tracking-wider text-ink-faint">{label}</p>
      <p className="mt-1 text-sm font-semibold tabular text-ink">{value}</p>
      {sublabel && <p className="mt-0.5 text-[11.5px] text-ink-faint">{sublabel}</p>}
    </div>
  );
}

const priorityVariant: Record<Priority, "danger" | "warning" | "accent" | "neutral"> = {
  critical: "danger",
  high: "warning",
  medium: "accent",
  low: "neutral",
};

export function PriorityBadge({ priority }: { priority: Priority }) {
  return (
    <Badge variant={priorityVariant[priority] ?? "neutral"} className="uppercase tracking-wider">
      {priority}
    </Badge>
  );
}

export function StatusBadge({ status }: { status: "ready" | "needs_attention" }) {
  return status === "ready" ? (
    <Badge variant="success">
      <span className="h-1.5 w-1.5 rounded-full bg-emerald" />
      Ready
    </Badge>
  ) : (
    <Badge variant="warning">
      <span className="h-1.5 w-1.5 rounded-full bg-amber" />
      Needs attention
    </Badge>
  );
}
