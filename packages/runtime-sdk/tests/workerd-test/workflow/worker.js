// Copyright (c) 2026 Cloudflare, Inc.
// Licensed under the Apache 2.0 license found in the LICENSE file or at:
//     https://opensource.org/licenses/Apache-2.0
import { RpcTarget } from 'cloudflare:workers';

import * as assert from 'node:assert';

// A stand-in for the Workflows engine's `WorkflowStep`. Like the real engine it runs the step
// callback over RPC, and it records the error it receives when the callback fails so the test
// can assert on what the engine would have seen.
class Context extends RpcTarget {
  constructor() {
    super();
    this.errors = [];
    this.sleeps = [];
  }

  async do(name, ...rest) {
    // do(name, callback) or do(name, config, callback)
    const callback = rest.at(-1);
    try {
      return await callback({
        step: { name, count: 1 },
        attempt: 1,
        config: {},
      });
    } catch (e) {
      this.errors.push({ step: name, name: e.name, message: e.message });
      // The engine rethrows so the workflow's `run()` can handle the error.
      throw e;
    }
  }

  async sleep(name, duration) {
    this.sleeps.push({ name, duration });
  }
}

// The engine treats a step error as non-retryable when
// `error.name === 'NonRetryableError' || error.message.startsWith('NonRetryableError')`
// (the name is folded into the message when the error is tunneled over RPC without enhanced
// error serialization).
function isNonRetryable(e) {
  return (
    e.name === 'NonRetryableError' || e.message.startsWith('NonRetryableError')
  );
}

function nonRetryableMessage(e) {
  return e.name === 'NonRetryableError'
    ? e.message
    : e.message.replace(/^NonRetryableError(: )?/, '');
}

export default {
  async test(ctrl, env) {
    const step = new Context();
    const result = await env.PythonWorkflow.run(
      { payload: { foo: 'bar' } },
      step
    );

    // --- What the engine saw -------------------------------------------------------------
    const byStep = Object.fromEntries(step.errors.map((e) => [e.step, e]));
    assert.deepStrictEqual(Object.keys(byStep).sort(), [
      'non_retryable',
      'non_retryable_no_message',
      'type_error',
    ]);

    // A Python NonRetryableError must arrive as a non-retryable JS error carrying the
    // Python message, not as a generic PythonError with a traceback.
    assert.ok(isNonRetryable(byStep.non_retryable), byStep.non_retryable);
    assert.strictEqual(nonRetryableMessage(byStep.non_retryable), 'do not retry');
    assert.ok(
      isNonRetryable(byStep.non_retryable_no_message),
      byStep.non_retryable_no_message
    );
    assert.strictEqual(
      nonRetryableMessage(byStep.non_retryable_no_message),
      ''
    );

    // Other Python exceptions are left alone: they arrive as Pyodide's PythonError with the
    // traceback as the message. Depending on the compatibility date the error is serialized
    // either as `{name: 'PythonError', message: '<traceback>'}` (enhanced error
    // serialization) or as `{name: 'Error', message: 'PythonError: <traceback>'}`.
    assert.ok(!isNonRetryable(byStep.type_error), byStep.type_error);
    assert.match(
      `${byStep.type_error.name}: ${byStep.type_error.message}`,
      /PythonError: Traceback/
    );
    assert.match(byStep.type_error.message, /TypeError: intentional type error/);

    // --- What the Python workflow saw once the engine rethrew ----------------------------
    assert.deepStrictEqual(result.non_retryable, {
      caught: 'NonRetryableError',
      message: 'do not retry',
    });
    assert.deepStrictEqual(result.non_retryable_no_message, {
      caught: 'NonRetryableError',
      message: '',
    });
    assert.strictEqual(result.type_error.caught, 'TypeError');
    assert.match(result.type_error.message, /intentional type error/);

    // The wrapped `step` still behaves like the real one otherwise.
    assert.deepStrictEqual(result.ok, { attempt: 1, payload: { foo: 'bar' } });
    assert.strictEqual(result.slept, true);
    assert.deepStrictEqual(step.sleeps, [{ name: 'nap', duration: '1 second' }]);
  },
};
