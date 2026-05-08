export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  return apiRequest<T>(path);
}

export async function apiPost<T, TBody extends object>(
  path: string,
  body: TBody,
): Promise<T> {
  return apiRequest<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function apiPatch<T, TBody extends object>(
  path: string,
  body: TBody,
): Promise<T> {
  return apiRequest<T>(path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");

  const response = await fetch(path, {
    ...init,
    headers,
  });

  const contentType = response.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    let message = response.statusText || "Request failed";
    if (payload && typeof payload === "object" && "detail" in payload) {
      const detail = payload.detail;
      message = typeof detail === "string" ? detail : JSON.stringify(detail);
    } else if (typeof payload === "string" && payload.trim()) {
      message = payload;
    }
    throw new ApiError(message, response.status);
  }

  return payload as T;
}
