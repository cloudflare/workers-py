# workers-runtime-sdk

Runtime SDK for Python Cloudflare Workers.

## ASGI response encoding

The ASGI adapter preserves application response bytes and `Content-Encoding`.
Applications and middleware are responsible for encoding their response bodies;
the adapter uses the Workers Fetch API's manual encoding mode to avoid
compressing an already-compressed response a second time.

Applications must negotiate supported encodings with the request's
`Accept-Encoding` header. Manual encoding does not make a gzip response
appropriate for an identity-only client.
