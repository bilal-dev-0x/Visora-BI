import type { ReactNode } from "react";
import { Reveal } from "@/components/motion/motion";

interface PageHeaderProps {
  title: string;
  description?: string;
  actions?: ReactNode;
  meta?: ReactNode;
}

export function PageHeader({ title, description, actions, meta }: PageHeaderProps) {
  return (
    <Reveal className="mb-7 flex flex-wrap items-end justify-between gap-4">
      <div className="space-y-1.5">
        <h1 className="text-[26px] font-semibold leading-tight tracking-[-0.02em] text-ink">
          {title}
        </h1>
        {description && (
          <p className="max-w-2xl text-[14px] leading-relaxed text-ink-muted">{description}</p>
        )}
        {meta && <div className="pt-1">{meta}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2.5">{actions}</div>}
    </Reveal>
  );
}
