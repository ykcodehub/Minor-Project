export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code?: string,
    public retryAfterSeconds?: number,
  ) {
    super(message);
  }
}
let csrfToken = "";
export function setCsrf(token: string) {
  csrfToken = token;
}
export const base = import.meta.env.VITE_API_BASE_URL || "/api/v1";
async function request(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  if (csrfToken && init.method && !["GET", "HEAD"].includes(init.method))
    headers.set("X-CSRF-Token", csrfToken);
  const response = await fetch(`${base}${path}`, {
    ...init,
    headers,
    credentials: "include",
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new ApiError(
      typeof error.message === "string"
        ? error.message
        : typeof error.detail === "string"
          ? error.detail
          : "The request could not be completed. Please try again.",
      response.status,
      typeof error.code === "string" ? error.code : undefined,
      Number(response.headers.get("Retry-After")) > 0
        ? Number(response.headers.get("Retry-After"))
        : undefined,
    );
  }
  return response;
}
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await request(path, init);
  return response.status === 204 ? (undefined as T) : response.json();
}
export interface Page<T> {
  items: T[];
  total: number | null;
}
export async function apiPage<T>(
  path: string,
  init: RequestInit = {},
): Promise<Page<T>> {
  const response = await request(path, init);
  const total = response.headers.get("X-Total-Count");
  return {
    items: await response.json(),
    total:
      total !== null && Number.isFinite(Number(total)) ? Number(total) : null,
  };
}
export const post = <T>(path: string, body?: unknown) =>
  api<T>(path, {
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
export async function download(path: string, name: string) {
  const response = await fetch(`${base}${path}`, { credentials: "include" });
  if (!response.ok) {
    const e = await response.json().catch(() => ({}));
    throw new ApiError(
      e.message || e.detail || "Download unavailable.",
      response.status,
    );
  }
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
