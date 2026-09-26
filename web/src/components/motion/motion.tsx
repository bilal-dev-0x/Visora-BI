import { useEffect, useState, type ReactNode } from "react";
import { animate, motion, useMotionValue, type HTMLMotionProps } from "motion/react";
import { cn, formatCompact, formatNumber } from "@/lib/utils";

type RevealProps = HTMLMotionProps<"div"> & {
  delay?: number;
  y?: number;
  duration?: number;
};

/**
 * Purposeful entrance: content lifts into place once, then stays put.
 * Used for page sections and card grids — never on every keystroke.
 */
export function Reveal({ delay = 0, y = 14, duration = 0.5, className, children, ...props }: RevealProps) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration, ease: [0.22, 1, 0.36, 1] }}
      {...props}
    >
      {children}
    </motion.div>
  );
}

/** Parent that staggers direct children on mount. */
export function Stagger({
  className,
  children,
  stagger = 0.06,
  delay = 0,
}: {
  className?: string;
  children: ReactNode;
  stagger?: number;
  delay?: number;
}) {
  return (
    <motion.div
      className={className}
      initial="hidden"
      animate="show"
      variants={{
        hidden: {},
        show: { transition: { staggerChildren: stagger, delayChildren: delay } },
      }}
    >
      {children}
    </motion.div>
  );
}

export function StaggerItem({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <motion.div
      className={className}
      variants={{
        hidden: { opacity: 0, y: 12 },
        show: { opacity: 1, y: 0, transition: { duration: 0.45, ease: [0.22, 1, 0.36, 1] } },
      }}
    >
      {children}
    </motion.div>
  );
}

/** KPI values count up once when they enter — quick and readable. */
export function AnimatedNumber({
  value,
  format = "int",
  className,
  duration = 0.9,
}: {
  value: number;
  format?: "int" | "compact" | "percent";
  className?: string;
  duration?: number;
}) {
  const motionValue = useMotionValue(0);
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    const controls = animate(motionValue, Number.isFinite(value) ? value : 0, {
      duration,
      ease: [0.22, 1, 0.36, 1],
    });
    const unsubscribe = motionValue.on("change", (latest) => setDisplay(latest));
    return () => {
      controls.stop();
      unsubscribe();
    };
  }, [value, motionValue, duration]);

  const rendered =
    format === "compact"
      ? formatCompact(display)
      : format === "percent"
        ? `${Math.round(display)}%`
        : formatNumber(Math.round(display));

  return <span className={cn("tabular", className)}>{rendered}</span>;
}

/** Route-level transition wrapper (fade + subtle rise). */
export function PageTransition({
  className,
  children,
  ...props
}: HTMLMotionProps<"div">) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -6 }}
      transition={{ duration: 0.32, ease: [0.22, 1, 0.36, 1] }}
      {...props}
    >
      {children}
    </motion.div>
  );
}
