# Binding Test Notes

## Bindings with full local tests

| Binding | Constructor (local) | Tests |
|---------|-------------------|-------|
| KV | `KvNamespace` | Full CRUD, metadata, list, pagination |
| R2 | `R2Bucket` | Full CRUD, metadata, list, ranges, multipart |
| D1 | `D1Database` | Prepare/bind/run, all/first/raw, batch, exec, sessions |
| Queue | `WorkerQueue` | Send various types, sendBatch, consumer receive |
| Durable Objects | `DurableObjectNamespace` | Storage KV, SQL, alarms, transactions, RPC |
| Analytics Engine | `LocalAnalyticsEngineDataset` | writeDataPoint with blobs/doubles/indexes |
| Rate Limiting | `Ratelimit` | limit() with different keys |
| Vectorize | `VectorizeIndexImpl` | Wrapper verification + method presence only (API calls need remote) |

## Bindings with wrapper-only tests

| Binding | Constructor (local) | Reason |
|---------|-------------------|--------|
| Images | `ImagesBindingImpl` | `input()` needs a ReadableStream of image bytes; `info()` needs a real image. Local simulator may not support transformations. |
| Images (hosted) | `HostedImagesBindingImpl` | Sub-binding via `env.IMAGES.hosted`. Methods: `image()`, `upload()`, `list()`. `upload()` needs image data, `image()` needs valid image ID, `list()` needs uploaded images. |
| Vectorize | `VectorizeIndexImpl` | "Binding VECTORIZE needs to be run remotely" — wrangler stubs it out locally. |

## Bindings not testable locally

| Binding | Reason | Config key |
|---------|--------|------------|
| AI | Always forces remote mode, crashes dev server without account_id | `ai` |
| Stream | Constructor is `Fetcher`, always remote | `stream` |
| Media Transforms | Always remote, no local simulation | `media` |

## Bindings not yet tested

| Binding | Config key | Notes |
|---------|-----------|-------|
| Email Send | `send_email` | Constructor is `Fetcher` locally but `SendEmail` in prod. Needs `_FetcherWrapper` + `callRpcMethod` fix locally. Tests exist on a separate branch (PR pending). |
| Email Routing | N/A (handler) | `email()` handler with `message.forward()`/`setReject()`. Tests exist on a separate branch (PR pending). |
| Service Bindings | `services` | Constructor is `Fetcher`. Needs JS service worker running alongside. Tests for `send`/`next`/`normalMethod` RPC shadowing exist on a separate branch (PR pending). |

## Known issues

### Images binding — methods need real image data
- `input(stream)` takes a `ReadableStream` of image bytes — requires actual image data to test.
- `info(url_or_blob)` inspects image metadata — requires a real image URL or blob.
- `hosted.upload(stream, options)` uploads an image — requires real image data.
- `hosted.image(id)` gets a handle — requires a valid uploaded image ID.
- `hosted.list(options)` lists images — needs uploaded images to return results.
- All could be tested with a small synthetic PNG, but the local simulator may not support full transformation/hosting operations.

### Analytics Engine — write-only in local dev
`writeDataPoint()` succeeds locally but data is not queryable from within the Worker. Analytics Engine data is only queryable via the GraphQL API externally. Tests verify the write doesn't error but can't verify the data was recorded.

### Rate Limiting — always succeeds locally
`limit()` returns `{success: true}` in local dev regardless of how many times it's called. The rate limiting logic is not simulated — it's a passthrough. Tests verify the call succeeds and returns the expected shape but can't verify actual rate limiting behavior.

### Media Transforms — remote only, no local simulation
The `media` binding does not support local simulation at all. Setting `remote: true` in the binding config enables remote mode but requires account authentication. Cannot be included in the shared test worker without blocking other tests.

### Stream — remote only, is a Fetcher
The `stream` binding's constructor is `Fetcher`. It always requires remote mode. Same account authentication issue as Media Transforms.

### AI — remote only, crashes dev server
The `ai` binding always forces remote mode. If no `account_id` is configured, wrangler fails to start the dev server entirely, blocking all other tests. Cannot be included in the shared test worker.
