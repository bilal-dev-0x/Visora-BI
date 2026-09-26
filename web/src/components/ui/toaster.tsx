import { Toaster as Sonner } from "sonner";
import { useAppStore } from "@/store/app-store";

export function Toaster() {
  const theme = useAppStore((state) => state.theme);
  const resolved =
    theme === "system"
      ? window.matchMedia("(prefers-color-scheme: light)").matches
        ? "light"
        : "dark"
      : theme;

  return (
    <Sonner
      theme={resolved}
      position="top-right"
      offset={14}
      gap={10}
      visibleToasts={4}
      toastOptions={{
        style: {
          background: "var(--surface-raised)",
          border: "1px solid var(--line-strong)",
          color: "var(--ink)",
          boxShadow: "0 18px 44px -20px rgba(0,0,0,0.65)",
          borderRadius: "10px",
          fontSize: "13px",
        },
        classNames: {
          title: "text-ink font-medium",
          description: "text-ink-muted",
          cancelButton: "text-ink-muted hover:bg-surface-hover",
          actionButton: "gradient-bg text-white",
        },
      }}
    />
  );
}
