import { toast } from "sonner";
import { ApiError } from "@/lib/api/client";

export function notifyError(error: unknown, fallback = "Something went wrong. Please try again.") {
  const message =
    error instanceof ApiError ? error.message : error instanceof Error ? error.message : fallback;
  toast.error("Request failed", { description: message });
}

export function notifySuccess(title: string, description?: string) {
  toast.success(title, description ? { description } : undefined);
}

export function notifyInfo(title: string, description?: string) {
  toast.info(title, description ? { description } : undefined);
}
