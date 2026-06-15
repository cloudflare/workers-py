// Copyright (c) 2025 Cloudflare, Inc.
// Licensed under the Apache 2.0 license found in the LICENSE file or at:
//     https://opensource.org/licenses/Apache-2.0
import { WorkerEntrypoint } from 'cloudflare:workers';

import * as assert from 'node:assert';

export class JsRpcTester extends WorkerEntrypoint {
  async noArgs() {
    return 'hello from js';
  }
  async oneArg(a) {
    return `${a}`;
  }
  async identity(x) {
    return x;
  }
  async handleResponse(resp) {
    // Verify that we receive a JS object here...
    assert.deepStrictEqual(resp.constructor.name, 'Response');
    return resp;
  }

  async handleRequest(req) {
    assert.deepStrictEqual(req.constructor.name, 'Request');
    return req;
  }
}

export default {
  async test(ctrl, env, ctx) {
    // JS types
    for (const val of [
      1,
      'test',
      [1, 2, 3],
      42,
      1.2345,
      false,
      true,
    ]) {
      const response = await env.PythonRpc.identity(val);
      assert.deepStrictEqual(response, val);
    }

    // Maps are converted to Python dicts and sent back as plain objects
    const mapResponse = await env.PythonRpc.identity(new Map([['key', 42]]));
    assert.deepStrictEqual(mapResponse, { key: 42 });

    const hasJsnull = await env.PythonRpc.supports_jsnull();
    const expectedNullish = hasJsnull ? null : undefined;

    const null_resp = await env.PythonRpc.identity(null);
    assert.strictEqual(null_resp, expectedNullish);

    const undef_resp = await env.PythonRpc.identity(undefined);
    assert.strictEqual(undef_resp, expectedNullish);

    const nested = await env.PythonRpc.identity({a: 1, b: null, c: {d: null}});
    assert.strictEqual(nested.a, 1);
    assert.strictEqual(nested.b, expectedNullish);
    assert.strictEqual(nested.c.d, expectedNullish);

    // Web/API Types
    const py_response = await env.PythonRpc.handle_response(
      new Response('this is a response')
    );
    assert.deepStrictEqual(await py_response.text(), 'this is a response');
    assert.equal(py_response.constructor.name, 'Response');

    const py_request = await env.PythonRpc.handle_request(
      new Request('https://test.com', { method: 'POST' })
    );
    assert.deepStrictEqual(py_request.method, 'POST');
    assert.equal(py_request.constructor.name, 'Request');
  },
};
