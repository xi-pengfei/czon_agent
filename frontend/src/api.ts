let csrfToken = "";

export function setCsrfToken(value: string) {
  csrfToken = value;
}

export async function api<T>(url: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers || {});
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const method = (options.method || "GET").toUpperCase();
  if (csrfToken && ["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    headers.set("X-CSRF-Token", csrfToken);
  }
  const response = await fetch(url, { ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || `请求失败 (${response.status})`);
  return data as T;
}

export async function apiResponse(url: string, options: RequestInit = {}) {
  const headers = new Headers(options.headers || {});
  const method = (options.method || "GET").toUpperCase();
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  if (csrfToken && ["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    headers.set("X-CSRF-Token", csrfToken);
  }
  return fetch(url, { ...options, headers });
}

export function uploadFile(file: File, onProgress: (percent: number) => void): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", "/api/upload");
    if (csrfToken) request.setRequestHeader("X-CSRF-Token", csrfToken);
    request.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(Math.round((event.loaded / event.total) * 100));
    };
    request.onload = () => {
      const data = JSON.parse(request.responseText || "{}");
      if (request.status >= 200 && request.status < 300) resolve(data);
      else reject(new Error(data.detail || "上传失败"));
    };
    request.onerror = () => reject(new Error("上传连接失败"));
    const body = new FormData();
    body.append("file", file);
    request.send(body);
  });
}

export function randomId() {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return [...bytes].map((value) => value.toString(16).padStart(2, "0")).join("");
}

export function formatTime(value?: string) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
  }).format(new Date(value));
}
