import type { ReactNode } from "react";
import { AlertTriangle, Inbox, RefreshCw } from "lucide-react";
import { motion } from "motion/react";
import { ApiError } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export function LoadingState({
  variant = "page",
  rows = 4,
}: {
  variant?: "page" | "cards" | "chart" | "table" | "detail";
  rows?: number;
}) {
  if (variant === "cards") {
    return (
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-28 rounded-xl" />
        ))}
      </div>
    );
  }

  if (variant === "chart") {
    return (
      <div className="grid gap-4 lg:grid-cols-2">
        <Skeleton className="h-72 rounded-xl" />
        <Skeleton className="h-72 rounded-xl" />
      </div>
    );
  }

  if (variant === "table") {
    return (
      <div className="space-y-3">
        <Skeleton className="h-10 w-full rounded-lg" />
        {Array.from({ length: rows }).map((_, index) => (
          <Skeleton key={index} className="h-14 w-full rounded-lg" />
        ))}
      </div>
    );
  }

  if (variant === "detail") {
    return (
      <div className="space-y-5">
        <Skeleton className="h-32 rounded-xl" />
        <div className="grid gap-4 lg:grid-cols-3">
          <Skeleton className="h-44 rounded-xl" />
          <Skeleton className="h-44 rounded-xl lg:col-span-2" />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <Skeleton className="h-9 w-64 rounded-lg" />
      <Skeleton className="h-4 w-96 max-w-full rounded" />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-28 rounded-xl" />
        ))}
      </div>
      <Skeleton className="h-72 rounded-xl" />
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
  title = "We couldn't load this view",
  compact = false,
}: {
  error: unknown;
  onRetry?: () => void;
  title?: string;
  compact?: boolean;
}) {
  const message =
    error instanceof ApiError
      ? error.message
      : error instanceof Error
        ? "Something went wrong while loading this view."
        : "Something went wrong while loading this view.";

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn(
        "panel flex flex-col items-center justify-center rounded-xl text-center",
        compact ? "gap-2 px-5 py-8" : "gap-3 px-6 py-14",
      )}
    >
      <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-rose/30 bg-rose/10 text-rose">
        <AlertTriangle className="h-5 w-5" />
      </div>
      <div className="space-y-1">
        <p className="text-sm font-semibold text-ink">{title}</p>
        <p className="max-w-md text-[13px] leading-relaxed text-ink-muted">{message}</p>
      </div>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry} className="mt-2">
          <RefreshCw className="h-3.5 w-3.5" />
          Try again
        </Button>
      )}
    </motion.div>
  );
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  secondaryAction,
  compact = false,
  className,
}: {
  icon?: ReactNode;
  title: string;
  description: string;
  action?: ReactNode;
  secondaryAction?: ReactNode;
  compact?: boolean;
  className?: string;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
      className={cn(
        "panel relative flex flex-col items-center justify-center overflow-hidden rounded-xl text-center",
        compact ? "gap-2.5 px-5 py-10" : "gap-3 px-6 py-16",
        className,
      )}
    >
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 -top-24 h-48 opacity-40 blur-3xl"
        style={{ backgroundImage: "var(--gradient-accent)" }}
      />
      {icon ??
        <div className="relative flex h-12 w-12 items-center justify-center rounded-xl border border-line-strong bg-surface-raised text-ink-muted">
          <Inbox className="h-5 w-5" />
        </div>}
      <div className="relative space-y-1.5">
        <p className="text-[15px] font-semibold tracking-tight text-ink">{title}</p>
        <p className="mx-auto max-w-md text-[13px] leading-relaxed text-ink-muted">{description}</p>
      </div>
      {(action || secondaryAction) && (
        <div className="relative mt-3 flex flex-wrap items-center justify-center gap-2.5">
          {action}
          {secondaryAction}
        </div>
      )}
    </motion.div>
  );
}
