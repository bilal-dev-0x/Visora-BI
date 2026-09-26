import { Outlet, useLocation } from "react-router-dom";
import { AnimatePresence, motion } from "motion/react";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/toaster";
import { Sidebar } from "./sidebar";
import { Topbar } from "./topbar";

export function AppShell() {
  const location = useLocation();

  return (
    <TooltipProvider delayDuration={150}>
      <div className="relative flex min-h-screen bg-canvas">
        <div
          aria-hidden
          className="pointer-events-none fixed right-0 top-0 h-[420px] w-[560px] opacity-[0.16] blur-[120px]"
          style={{ backgroundImage: "var(--gradient-accent)" }}
        />
        <Sidebar />
        <div className="relative flex min-w-0 flex-1 flex-col">
          <Topbar />
          <main className="mx-auto w-full max-w-[1460px] flex-1 px-7 py-7">
            <AnimatePresence mode="wait" initial={false}>
              <motion.div
                key={location.pathname}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
              >
                <Outlet />
              </motion.div>
            </AnimatePresence>
          </main>
          <footer className="border-t border-line px-7 py-4">
            <div className="mx-auto flex max-w-[1460px] items-center justify-between gap-4 text-[11.5px] text-ink-faint">
              <span>
                VISORA BI · <span className="text-ink-muted">Make the hidden obvious.</span>
              </span>
              <span className="mono">local-first · evidence-backed</span>
            </div>
          </footer>
        </div>
        <Toaster />
      </div>
    </TooltipProvider>
  );
}
