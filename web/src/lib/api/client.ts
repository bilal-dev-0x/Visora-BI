import type { ApiErrorBody } from "./types";

export const API_BASE = "/api/v1";

/** Human-readable API failure. `message` is always safe to show in the UI. */
export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly detail?: unknown;

  constructor(status: number, code: string, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

function isApiErrorBody(value: unknown): value is ApiErrorBody {
  return (
    typeof value === "object" &&
    value !== null &&
    "error" in value &&
    typeof (value as ApiErrorBody).error?.message === "string"
  );
}

async function parseBody(response: Response): Promise<unknown> {
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    try {
      return await response.json();
    } catch {
      return null;
    }
  }
  return await response.text();
}

export async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init.body && !(init.body instanceof FormData)
          ? { "Content-Type": "application/json" }
          : {}),
        ...init.headers,
      },
    });
  } catch {
    throw new ApiError(
      0,
      "network_error",
      "Can't reach the VISORA API. Make sure the backend is running, then try again.",
    );
  }

  const body = await parseBody(response);

  if (!response.ok) {
    if (isApiErrorBody(body)) {
      throw new ApiError(response.status, body.error.code, body.error.message, body.error.detail);
    }
    throw new ApiError(
      response.status,
      "request_failed",
      "VISORA could not complete that request. Please try again.",
    );
  }

  return body as T;
}

export function get<T>(path: string): Promise<T> {
  return request<T>(path);
}

export function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export function del<T>(path: string): Promise<T> {
  return request<T>(path, { method: "DELETE" });
}

export interface UploadOptions {
  onProgress?: (percent: number, loaded: number, total: number) => void;
  signal?: AbortSignal;
}

/** Multipart upload with real progress events + cancellation (XHR). */
export function upload<T>(
  path: string,
  file: File,
  { onProgress, signal }: UploadOptions = {},
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    if (signal?.aborted) {
      reject(new ApiError(0, "upload_cancelled", "Upload cancelled."));
      return;
    }

    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}${path}`);
    xhr.setRequestHeader("Accept", "application/json");

    const abort = () => {
      xhr.abort();
    };
    signal?.addEventListener("abort", abort, { once: true });

    const cleanup = () => signal?.removeEventListener("abort", abort);

    xhr.upload.addEventListener("progress", (event) => {
      if (!event.lengthComputable) return;
      const percent = Math.round((event.loaded / event.total) * 100);
      onProgress?.(percent, event.loaded, event.total);
    });

    xhr.addEventListener("load", () => {
      cleanup();
      let parsed: unknown = null;
      try {
        parsed = xhr.responseText ? JSON.parse(xhr.responseText) : null;
      } catch {
        parsed = null;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress?.(100, 1, 1);
        resolve(parsed as T);
        return;
      }
      if (isApiErrorBody(parsed)) {
        reject(new ApiError(xhr.status, parsed.error.code, parsed.error.message, parsed.error.detail));
      } else {
        reject(
          new ApiError(
            xhr.status,
            "upload_failed",
            "VISORA could not save that file. Please try again.",
          ),
        );
      }
    });

    xhr.addEventListener("error", () => {
      cleanup();
      reject(
        new ApiError(
          0,
          "network_error",
          "The upload failed because the API could not be reached.",
        ),
      );
    });

    xhr.addEventListener("abort", () => {
      cleanup();
      reject(new ApiError(0, "upload_cancelled", "Upload cancelled."));
    });

    const form = new FormData();
    form.append("file", file, file.name);
    xhr.send(form);
  });
}

/** Fetch a binary attachment (report downloads) with friendly errors. */
export async function download(path: string, fallbackName: string): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`);
  } catch {
    throw new ApiError(0, "network_error", "The download could not reach the VISORA API.");
  }
  if (!response.ok) {
    const body = await parseBody(response);
    if (isApiErrorBody(body)) {
      throw new ApiError(response.status, body.error.code, body.error.message);
    }
    throw new ApiError(response.status, "download_failed", "That report could not be downloaded.");
  }
  const blob = await response.blob();
  const disposition = response.headers.get("content-disposition") ?? "";
  const match = /filename="?([^"]+)"?/.exec(disposition);
  const name = match?.[1] ?? fallbackName;
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
