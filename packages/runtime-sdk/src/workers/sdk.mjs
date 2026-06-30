// AUTO-GENERATED FILE - DO NOT EDIT DIRECTLY
// Source: ts/sdk.ts
// Regenerate: python scripts/compile_js_sdk.py
const waitUntilPatched = /* @__PURE__ */ new WeakSet();
function patchWaitUntil(ctx) {
  let tag;
  try {
    tag = Object.prototype.toString.call(ctx);
  } catch (_e) {
  }
  if (tag !== "[object ExecutionContext]") {
    return;
  }
  if (waitUntilPatched.has(ctx)) {
    return;
  }
  const origWaitUntil = ctx.waitUntil.bind(ctx);
  function waitUntil(p) {
    origWaitUntil(
      (async function() {
        if ("copy" in p) {
          p = p.copy();
        }
        await p;
        if ("destroy" in p) {
          p.destroy();
        }
      })()
    );
  }
  ctx.waitUntil = waitUntil;
  waitUntilPatched.add(ctx);
}
export {
  patchWaitUntil
};
