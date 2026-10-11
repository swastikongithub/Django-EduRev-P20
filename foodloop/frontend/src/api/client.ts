// A small wrapper around fetch: JSON in, JSON out, and one error type with friendly messages.

export class ApiError extends Error {
  status: number;
  /** Field name → message, for highlighting form inputs ("kitchen.fssai_number", "price_paise"...). */
  fieldErrors: Record<string, string>;

  constructor(status: number, message: string, fieldErrors: Record<string, string> = {}) {
    super(message);
    this.status = status;
    this.fieldErrors = fieldErrors;
  }
}

const FALLBACK_MESSAGES: Record<number, string> = {
  401: "Please log in to continue.",
  403: "You don't have access to this.",
  404: "We couldn't find that.",
  429: "Too many attempts. Please wait a few minutes.",
  500: "Something went wrong on our side. Please try again.",
};

interface Options {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: unknown;
  formData?: FormData;
  signal?: AbortSignal;
}

export async function api<T>(path: string, { method = "GET", body, formData, signal }: Options = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      credentials: "same-origin",
      headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: body !== undefined ? JSON.stringify(body) : formData,
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, "Can't reach FoodLoop. Check your internet connection and try again.");
  }

  if (response.status === 204) return undefined as T;
  let data: unknown = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }
  if (!response.ok) {
    const payload = (data ?? {}) as { detail?: unknown; errors?: { field: string; message: string }[] };
    const fieldErrors: Record<string, string> = {};
    for (const item of payload.errors ?? []) {
      fieldErrors[item.field] ??= item.message;
    }
    const message =
      typeof payload.detail === "string"
        ? payload.detail
        : (FALLBACK_MESSAGES[response.status] ?? FALLBACK_MESSAGES[500]);
    throw new ApiError(response.status, message, fieldErrors);
  }
  return data as T;
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "Something went wrong. Please try again.";
}

export function toQuery(params: Record<string, string | number | string[] | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) value.forEach((item) => search.append(key, item));
    else search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}
