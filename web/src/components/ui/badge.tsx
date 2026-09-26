import type { HTMLAttributes } from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-[11px] font-medium tracking-wide transition-colors",
  {
    variants: {
      variant: {
        neutral: "border-line bg-surface-sunken text-ink-muted",
        accent: "border-accent/30 bg-accent-soft text-accent",
        success: "border-emerald/30 bg-emerald/10 text-emerald",
        warning: "border-amber/30 bg-amber/10 text-amber",
        danger: "border-rose/30 bg-rose/10 text-rose",
        outline: "border-line-strong text-ink-muted",
        gradient: "border-transparent text-white gradient-bg",
      },
    },
    defaultVariants: { variant: "neutral" },
  },
);

export interface BadgeProps
  extends HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
