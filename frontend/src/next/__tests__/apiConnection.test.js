import { afterEach, describe, expect, it, vi } from 'vitest';
import { apiRequest } from '../api.js';
import { connection, markOnline } from '../stores/connection.js';

// PLAN-078f f4: a request that never gets an answer is "connection lost", not a mystery.

const json = (status, body) => ({ ok: status < 400, status, headers: { get: () => 'application/json' }, json: async () => body });

afterEach(() => {
  vi.unstubAllGlobals();
  markOnline();
});

describe('apiRequest and the connection state', () => {
  it('turns a network failure into a clear error and marks the connection lost', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch'); }));
    const error = await apiRequest('/api/v1/me').catch((cause) => cause);
    expect(error.network).toBe(true);
    expect(error.status).toBe(0);
    expect(error.message).toContain('连接中断');
    expect(connection.offline.value).toBe(true);
  });

  it('marks the connection back as fine on the next answer, even an error answer', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch'); }));
    await apiRequest('/api/v1/me').catch(() => {});
    expect(connection.offline.value).toBe(true);
    vi.stubGlobal('fetch', vi.fn(async () => json(500, { detail: 'oops' })));
    await apiRequest('/api/v1/me').catch(() => {});
    expect(connection.offline.value).toBe(false); // the server answered; it is reachable
  });

  it('leaves a request the caller aborted alone', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw Object.assign(new Error('aborted'), { name: 'AbortError' }); }));
    const error = await apiRequest('/api/v1/me').catch((cause) => cause);
    expect(error.name).toBe('AbortError');
    expect(connection.offline.value).toBe(false);
  });

  it('follows the browser\'s own online and offline events', () => {
    window.dispatchEvent(new Event('offline'));
    expect(connection.offline.value).toBe(true);
    window.dispatchEvent(new Event('online'));
    expect(connection.offline.value).toBe(false);
  });
});
