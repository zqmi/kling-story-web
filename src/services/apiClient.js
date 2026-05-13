export function apiUrl(path) {
  const base = import.meta.env.VITE_API_BASE_URL ?? ''
  const normalizedBase = String(base).replace(/\/$/, '')
  const p = path.startsWith("/") ? path : `/${path}`
  if (!normalizedBase) return p
  return `${normalizedBase}${p}`
}

/**
 * 静态资源 URL（如 `/media/generated-visual/...`）。
 * 若将 `VITE_API_BASE_URL` 写成 `http://host:port/api`，用 `apiUrl` 拼 `/media/...` 会得到错误的 `…/api/media/…`；
 * 本函数在检测到以 `/api` 结尾时去掉该段，使媒体仍指向服务根路径。
 */
export function staticAssetUrl(path) {
  let base = String(import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')
  if (base.endsWith('/api')) {
    base = base.slice(0, -4)
  }
  const p = path.startsWith('/') ? path : `/${path}`
  if (!base) return p
  return `${base}${p}`
}

/** FastAPI 常用 `detail` 字符串或校验错误数组；兼容 `message` */
function httpErrorMessage(data, r) {
  if (typeof data === "object" && data !== null) {
    if (data.message != null && String(data.message).trim()) {
      return String(data.message)
    }
    const d = data.detail
    if (typeof d === "string" && d.trim()) {
      return d
    }
    if (Array.isArray(d) && d.length) {
      return d
        .map((item) => (item && typeof item === "object" && item.msg != null ? String(item.msg) : JSON.stringify(item)))
        .join("；")
    }
  }
  return `${r.status} ${r.statusText}`
}

export async function apiPost(path, body, init = {}) {
  const url = apiUrl(path)
  const r = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(init.headers || {}),
    },
    body: JSON.stringify(body),
    ...init,
  })
  const text = await r.text()
  let data = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = text
    }
  }
  if (!r.ok) {
    const msg = httpErrorMessage(data, r)
    const err = new Error(msg)
    err.status = r.status
    err.body = data
    throw err
  }
  return { response: r, data }
}

export async function apiGet(path, init = {}) {
  const url = apiUrl(path)
  const r = await fetch(url, {
    method: 'GET',
    headers: { ...(init.headers || {}) },
    ...init,
    method: 'GET',
  })
  const text = await r.text()
  let data = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = text
    }
  }
  if (!r.ok) {
    const msg = httpErrorMessage(data, r)
    const err = new Error(msg)
    err.status = r.status
    err.body = data
    throw err
  }
  return { response: r, data }
}
