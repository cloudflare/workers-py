// Javascript helper functions for workers-runtime-sdk
// This file is compiled to src/workers/sdk.mjs via scripts/compile_js_sdk.py

// Pyodide proxy future — supports copy/destroy for proxy lifecycle management
type PyFuture<T> = Promise<T> & {
  copy(): PyFuture<T>;
  destroy(): void;
};

const waitUntilPatched = new WeakSet();

export function patchWaitUntil(ctx: {
  waitUntil: (p: Promise<void> | PyFuture<void>) => void;
}): void {
  let tag;
  try {
    tag = Object.prototype.toString.call(ctx);
  } catch (_e) {}
  if (tag !== '[object ExecutionContext]') {
    return;
  }
  if (waitUntilPatched.has(ctx)) {
    return;
  }
  const origWaitUntil: (p: Promise<void>) => void = ctx.waitUntil.bind(ctx);
  function waitUntil(p: Promise<void> | PyFuture<void>): void {
    origWaitUntil(
      (async function (): Promise<void> {
        if ('copy' in p) {
          p = p.copy();
        }
        await p;
        if ('destroy' in p) {
          p.destroy();
        }
      })()
    );
  }
  ctx.waitUntil = waitUntil;
  waitUntilPatched.add(ctx);
}
