/**
 * The string code of a FastAPI `HTTPException(status, "some_code")`.
 *
 * `ApiError.detail` is the WHOLE response body, so the code is at
 * `err.detail.detail`, never at `err.detail`. Comparing `err.detail` with a
 * string is always false — which is how «войти в Didox» stopped happening on its
 * own: every `didox_session_required` fell through to «Не удалось подписать».
 *
 * Structural rather than `instanceof ApiError`, so it imports nothing and can be
 * tested under plain `node --test`.
 */
export function detailCode(err: unknown): string | null {
  if (typeof err !== "object" || err === null) return null;
  const body = (err as { detail?: unknown }).detail;
  if (typeof body !== "object" || body === null) return null;
  const inner = (body as { detail?: unknown }).detail;
  return typeof inner === "string" ? inner : null;
}
