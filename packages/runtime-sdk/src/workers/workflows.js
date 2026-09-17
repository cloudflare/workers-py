// JavaScript helpers for Python Workflows

const NON_RETRYABLE_ERROR_NAME = "NonRetryableError";

function isPythonError(e) {
  return (
    e instanceof Error &&
    e.constructor?.name === "PythonError" &&
    typeof e.type === "string"
  );
}

// Extract the message the user passed to the Python exception from the
// traceback stored in `PythonError.message`.
//
// The last non-empty line of a formatted traceback is
// `<qualified.ExceptionType>: <message>`, or just `<qualified.ExceptionType>`
// when the exception was raised without a message. For example, given
//
//   Traceback (most recent call last):
//     File "/session/metadata/worker.py", line 19, in non_retryable
//       raise NonRetryableError("do not retry")
//   workers.workflows.NonRetryableError: do not retry
//
// this returns "do not retry", and given
//
//   Traceback (most recent call last):
//     File "/session/metadata/worker.py", line 34, in no_message
//       raise NonRetryableError()
//   workers.workflows.NonRetryableError
//
// it returns "".
function pythonExceptionMessage(e) {
  const lines = e.message.split("\n").filter((line) => line.trim() !== "");
  const last = lines.at(-1) ?? "";
  const sep = last.indexOf(": ");
  return sep === -1 ? "" : last.slice(sep + 2);
}

// Wraps a Python step callback passed to `WorkflowStep.do()`.
//
// If the error thrown is a Python NonRetryable error, translate it into a JS
// error that the engine will recognize as non retryable. Leave other errors
// alone.
export function wrapWorkflowStepCallback(pyCallback) {
  return async function (...args) {
    try {
      return await pyCallback(...args);
    } catch (e) {
      if (isPythonError(e) && e.type === NON_RETRYABLE_ERROR_NAME) {
        const err = new Error(pythonExceptionMessage(e));
        err.name = NON_RETRYABLE_ERROR_NAME;
        throw err;
      }
      throw e;
    }
  };
}

// Wraps the `WorkflowStep` RPC stub passed to a Python
// `WorkflowEntrypoint.run()` so that the callback given to `step.do()` goes
// through `wrapWorkflowStepCallback`.
//
// Because the wrapped `do` returns the stub's own promise, a Python callback
// passed to it keeps exactly the lifetime it would have had without the
// wrapper.
export function wrapWorkflowStep(step) {
  // RPC stubs are callable, so `typeof step` is 'function'.
  if (
    step === null ||
    (typeof step !== "object" && typeof step !== "function")
  ) {
    return step;
  }
  return new Proxy(step, {
    apply(target, thisArg, args) {
      return Reflect.apply(target, thisArg, args);
    },
    get(target, prop) {
      if (prop !== "do") {
        return Reflect.get(target, prop);
      }
      return function (name, ...rest) {
        const args = rest.map((arg) =>
          typeof arg === "function" ? wrapWorkflowStepCallback(arg) : arg
        );
        return target.do(name, ...args);
      };
    },
  });
}
