import { motion } from "motion/react";
import { cn } from "@/lib/utils";

/**
 * The VISORA mark (supplied asset, served from /public) with a
 * restrained materialization-in animation — an echo of the supplied
 * logo reveal, sized for chrome rather than a full-screen splash.
 */
export function LogoMark({
  size = 30,
  className,
  animate = true,
}: {
  size?: number;
  className?: string;
  animate?: boolean;
}) {
  return (
    <motion.img
      src="/visora-mark.png"
      alt="VISORA BI"
      width={size}
      height={size}
      className={cn("rounded-[9px] border border-line shadow-[0_6px_18px_-8px_rgba(99,102,241,0.8)]", className)}
      style={{ width: size, height: size }}
      initial={animate ? { opacity: 0, scale: 0.82, rotate: -6 } : false}
      animate={animate ? { opacity: 1, scale: 1, rotate: 0 } : undefined}
      transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
    />
  );
}

const WORDMARK = "VISORA".split("");

export function Wordmark({ compact = false, className }: { compact?: boolean; className?: string }) {
  return (
    <span className={cn("flex items-baseline gap-1.5 leading-none", className)}>
      <span className="gradient-text text-[13.5px] font-semibold tracking-[0.26em]">
        {WORDMARK.map((letter, index) => (
          <motion.span
            key={`${letter}-${index}`}
            className="inline-block"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.06 + index * 0.045, duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
          >
            {letter}
          </motion.span>
        ))}
      </span>
      {!compact && (
        <motion.span
          className="text-[11px] font-medium tracking-[0.3em] text-ink-faint"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.4, duration: 0.4 }}
        >
          BI
        </motion.span>
      )}
    </span>
  );
}

export function BrandLockup({ compact = false, className }: { compact?: boolean; className?: string }) {
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <LogoMark size={compact ? 26 : 30} />
      {!compact && <Wordmark />}
    </div>
  );
}
