import { vi } from 'vitest';

// Stub fetch with URL+method routing. Falls back to 200 {} for unmatched calls.
// routes: [{url, method?, body?, status?, ok?}]
// url can be a string (exact) or RegExp.
export function makeFetchMock(routes = []) {
  return vi.fn().mockImplementation((url, opts = {}) => {
    const method = (opts?.method || 'GET').toUpperCase();
    for (const route of routes) {
      const urlOk = route.url instanceof RegExp ? route.url.test(url) : url === route.url;
      const methodOk = !route.method || route.method.toUpperCase() === method;
      if (urlOk && methodOk) {
        const body = typeof route.body === 'function' ? route.body(url, opts) : (route.body ?? {});
        return Promise.resolve({ok: route.ok !== false, status: route.status ?? 200, json: () => Promise.resolve(body)});
      }
    }
    throw new Error(`Unexpected fetch: ${method} ${url}`);
  });
}
