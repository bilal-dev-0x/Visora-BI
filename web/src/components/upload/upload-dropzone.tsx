import { useCallback, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { CheckCircle2, FileSpreadsheet, RotateCcw, Upload, X } from "lucide-react";
import { ApiError } from "@/lib/api/client";
import { api } from "@/lib/api/endpoints";
import type { DatasetSummary } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/controls";
import { notifyInfo } from "@/lib/notify";
import { cn, formatBytes } from "@/lib/utils";

type Phase = "idle" | "uploading" | "processing" | "success" | "error";

const ACCEPTED = [".csv", ".xlsx", ".xlsm"];

interface UploadDropzoneProps {
  maxBytes: number;
  onUploaded: (dataset: DatasetSummary, warning: string | null) => void;
  compact?: boolean;
}

export function UploadDropzone({ maxBytes, onUploaded, compact = false }: UploadDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const retryRef = useRef<File | null>(null);

  const [phase, setPhase] = useState<Phase>("idle");
  const [dragging, setDragging] = useState(false);
  const [progress, setProgress] = useState(0);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  const reset = useCallback(() => {
    setPhase("idle");
    setProgress(0);
    setFile(null);
    setError(null);
    retryRef.current = null;
  }, []);

  const startUpload = useCallback(
    async (picked: File) => {
      const extension = `.${picked.name.split(".").pop()?.toLowerCase() ?? ""}`;
      if (!ACCEPTED.includes(extension)) {
        const apiError = new ApiError(
          400,
          "unsupported_file_type",
          "That file type isn't supported. Please upload a .csv, .xlsx or .xlsm file.",
        );
        setError(apiError);
        setFile(picked);
        setPhase("error");
        return;
      }
      if (picked.size > maxBytes) {
        const apiError = new ApiError(
          413,
          "file_too_large",
          `"${picked.name}" is ${formatBytes(picked.size)}, over the ${formatBytes(maxBytes)} upload limit.`,
        );
        setError(apiError);
        setFile(picked);
        setPhase("error");
        return;
      }

      retryRef.current = picked;
      setFile(picked);
      setError(null);
      setProgress(0);
      setPhase("uploading");

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const result = await api.uploadDataset(picked, {
          signal: controller.signal,
          onProgress: (percent) => {
            setProgress(percent);
            if (percent >= 100) setPhase("processing");
          },
        });
        setProgress(100);
        setPhase("success");
        setTimeout(() => onUploaded(result.dataset, result.warning), 620);
      } catch (caught) {
        if (caught instanceof ApiError && caught.code === "upload_cancelled") {
          notifyInfo("Upload cancelled", `${picked.name} was not saved.`);
          reset();
          return;
        }
        setError(
          caught instanceof ApiError
            ? caught
            : new ApiError(0, "upload_failed", "The upload failed. Please try again."),
        );
        setPhase("error");
      } finally {
        abortRef.current = null;
      }
    },
    [maxBytes, onUploaded, reset],
  );

  const handleFiles = (files: FileList | null) => {
    const picked = files?.[0];
    if (picked) void startUpload(picked);
  };

  const cancel = () => {
    abortRef.current?.abort();
  };

  const busy = phase === "uploading" || phase === "processing";

  return (
    <div className={cn("relative", compact ? "max-w-full" : "max-w-3xl")}>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED.join(",")}
        className="sr-only"
        onChange={(event) => {
          handleFiles(event.target.files);
          event.target.value = "";
        }}
        disabled={busy}
      />

      <AnimatePresence mode="wait">
        {phase === "success" ? (
          <motion.div
            key="success"
            initial={{ opacity: 0, scale: 0.97 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.98 }}
            transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
            className="relative flex items-center gap-4 overflow-hidden rounded-xl border border-emerald/40 bg-emerald/8 px-5 py-5"
          >
            <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-emerald/40 bg-emerald/15 text-emerald">
              <CheckCircle2 className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-ink">Dataset ready</p>
              <p className="truncate text-[13px] text-ink-muted">
                {file?.name} was saved and ingested.
              </p>
            </div>
          </motion.div>
        ) : phase === "error" ? (
          <motion.div
            key="error"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.24 }}
            className="rounded-xl border border-rose/40 bg-rose/8 px-5 py-5"
          >
            <div className="flex items-start gap-3.5">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-rose/40 bg-rose/12 text-rose">
                <X className="h-4.5 w-4.5" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-ink">Upload didn't finish</p>
                <p className="mt-1 text-[13px] leading-relaxed text-ink-muted">
                  {error?.message ?? "Something went wrong while uploading this file."}
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    variant="primary"
                    onClick={() => retryRef.current && void startUpload(retryRef.current)}
                  >
                    <RotateCcw className="h-3.5 w-3.5" />
                    Retry upload
                  </Button>
                  <Button size="sm" variant="ghost" onClick={reset}>
                    Dismiss
                  </Button>
                </div>
              </div>
            </div>
          </motion.div>
        ) : (
          <motion.div
            key="idle-dropzone"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.24 }}
            onDragOver={(event) => {
              event.preventDefault();
              if (!busy) setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDragging(false);
              if (!busy) handleFiles(event.dataTransfer.files);
            }}
            onClick={() => !busy && inputRef.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={(event) => {
              if ((event.key === "Enter" || event.key === " ") && !busy) {
                event.preventDefault();
                inputRef.current?.click();
              }
            }}
            aria-label="Upload a dataset"
            className={cn(
              "group relative cursor-pointer overflow-hidden rounded-xl border border-dashed px-6 text-center transition-all duration-300 outline-none",
              compact ? "py-8" : "py-12",
              dragging
                ? "border-cyan/70 bg-cyan/8 scale-[1.005]"
                : busy
                  ? "cursor-default border-line bg-surface"
                  : "border-line-strong bg-surface hover:border-accent/50 hover:bg-surface-raised",
            )}
          >
            <div
              aria-hidden
              className={cn(
                "pointer-events-none absolute inset-x-0 -top-24 h-40 blur-3xl transition-opacity duration-500",
                dragging ? "opacity-60" : "opacity-25 group-hover:opacity-45",
              )}
              style={{ backgroundImage: "var(--gradient-accent)" }}
            />

            <div className="relative flex flex-col items-center gap-3">
              <motion.div
                animate={dragging ? { y: -4, scale: 1.05 } : { y: 0, scale: 1 }}
                transition={{ type: "spring", stiffness: 320, damping: 22 }}
                className="flex h-12 w-12 items-center justify-center rounded-xl border border-line-strong bg-surface-raised text-ink-muted shadow-[0_10px_30px_-16px_rgba(99,102,241,0.9)]"
              >
                <Upload className="h-5 w-5" />
              </motion.div>

              {busy ? (
                <div className="w-full max-w-md space-y-3">
                  <p className="text-sm font-medium text-ink">
                    {phase === "uploading" ? `Uploading ${file?.name}` : "Preparing dataset…"}
                  </p>
                  <Progress value={progress} className="h-2" />
                  <div className="flex items-center justify-between text-[12px] text-ink-faint">
                    <span className="mono tabular">
                      {phase === "uploading" ? `${progress}%` : "ingesting"}
                    </span>
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        cancel();
                      }}
                      className="rounded-md px-2 py-1 text-ink-muted transition-colors hover:bg-surface-hover hover:text-ink"
                    >
                      Cancel upload
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <p className="text-[15px] font-medium text-ink">
                    Drop your CSV or Excel file here
                  </p>
                  <p className="text-[13px] text-ink-muted">
                    or <span className="text-accent underline underline-offset-2">browse files</span> ·{" "}
                    {ACCEPTED.join(", ")} · up to {formatBytes(maxBytes)}
                  </p>
                  <div className="mt-1 flex items-center gap-1.5 text-[11.5px] text-ink-faint">
                    <FileSpreadsheet className="h-3.5 w-3.5" />
                    Files stay on this machine — local-first by design
                  </div>
                </>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
