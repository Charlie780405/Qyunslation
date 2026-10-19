// PLAN-078f f7: SHA-256 of a file in the browser, so the server can hand back the pre-check it already holds
// for the same bytes. Above the limit (or without Web Crypto, which needs a secure context) we skip it and the
// upload simply goes through as before.

export const HASH_LIMIT_BYTES = 200 * 1024 * 1024;

export async function sha256Hex(file, { limit = HASH_LIMIT_BYTES } = {}) {
  const subtle = globalThis.crypto?.subtle;
  if (!subtle || !file || file.size > limit) return null;
  try {
    const digest = await subtle.digest('SHA-256', await file.arrayBuffer());
    return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
  } catch {
    return null; // hashing is an optimisation, never a reason to refuse an upload
  }
}
