# CHANGELOG

<!-- version list -->

## v1.5.2 (2026-07-01)

### Bug Fixes

- Ensure that ctx and env __init__ arguments are always wrapped
  ([#131](https://github.com/cloudflare/workers-py/pull/131),
  [`465c702`](https://github.com/cloudflare/workers-py/commit/465c7029d7b7d5ca75afb1648d9a96433a8a9a13))


## v1.5.1 (2026-06-29)

### Bug Fixes

- Ensure self.env and top-level env uses a same class
  ([#136](https://github.com/cloudflare/workers-py/pull/136),
  [`e627c11`](https://github.com/cloudflare/workers-py/commit/e627c11f58c572f6ee5df97e423928ee4423d2e9))

- Update FetchResponse.headers to return HTTPMessage
  ([#136](https://github.com/cloudflare/workers-py/pull/136),
  [`e627c11`](https://github.com/cloudflare/workers-py/commit/e627c11f58c572f6ee5df97e423928ee4423d2e9))


## v1.5.0 (2026-06-23)

### Features

- Apply bindings wrapper to AI bindings ([#130](https://github.com/cloudflare/workers-py/pull/130),
  [`79eeaf9`](https://github.com/cloudflare/workers-py/commit/79eeaf94ab02e4208372a7d3f57ba34248421c93))

- Apply bindings wrapper to Images, RateLimit, and Analytics Engine
  ([#130](https://github.com/cloudflare/workers-py/pull/130),
  [`79eeaf9`](https://github.com/cloudflare/workers-py/commit/79eeaf94ab02e4208372a7d3f57ba34248421c93))

- Wrap AI, Images, Analytics Engine, Vectorize and RateLimit Bindings to accept native Python
  objects ([#130](https://github.com/cloudflare/workers-py/pull/130),
  [`79eeaf9`](https://github.com/cloudflare/workers-py/commit/79eeaf94ab02e4208372a7d3f57ba34248421c93))


## v1.4.3 (2026-06-18)

### Bug Fixes

- Ensure Worker subclasses are wrapped only once
  ([#126](https://github.com/cloudflare/workers-py/pull/126),
  [`af8ec42`](https://github.com/cloudflare/workers-py/commit/af8ec42eed1e2bbe6da1dbd537eb7a475f7071fb))


## v1.4.2 (2026-06-18)

### Bug Fixes

- Make iterables work correctly when returned from rpc call
  ([#127](https://github.com/cloudflare/workers-py/pull/127),
  [`36dc659`](https://github.com/cloudflare/workers-py/commit/36dc659d6ba394d75e3d11b3e78e2b08fcd91c9f))


## v1.4.1 (2026-06-18)

### Bug Fixes

- Fix ReadableStream being incorrectly wrapped by BindingWrapper
  ([#128](https://github.com/cloudflare/workers-py/pull/128),
  [`85ad1f3`](https://github.com/cloudflare/workers-py/commit/85ad1f33d5f23fd932c0eac5cc5a9f7d39159423))


## v1.4.0 (2026-06-17)

### Features

- Auto-convert Python objects that are passed to/from Queue
  ([#123](https://github.com/cloudflare/workers-py/pull/123),
  [`906a10a`](https://github.com/cloudflare/workers-py/commit/906a10a7392f9d823a1b6bba044300ece8763401))

- Auto-convert Python objects that are passed to/from Queue Binding
  ([#123](https://github.com/cloudflare/workers-py/pull/123),
  [`906a10a`](https://github.com/cloudflare/workers-py/commit/906a10a7392f9d823a1b6bba044300ece8763401))


## v1.3.0 (2026-06-15)

### Features

- **runtime-sdk**: Revise type conversion for Durable Object binding
  ([#112](https://github.com/cloudflare/workers-py/pull/112),
  [`b12650e`](https://github.com/cloudflare/workers-py/commit/b12650ef91bb71f4ebebd9827bad2d1f0946fd62))

- **runtime-sdk**: Revise type conversion to support bindings more natively
  ([#112](https://github.com/cloudflare/workers-py/pull/112),
  [`b12650e`](https://github.com/cloudflare/workers-py/commit/b12650ef91bb71f4ebebd9827bad2d1f0946fd62))

- **runtime-sdk**: Update js object conversion logic to support cloudflare bindings more natively.
  ([#112](https://github.com/cloudflare/workers-py/pull/112),
  [`b12650e`](https://github.com/cloudflare/workers-py/commit/b12650ef91bb71f4ebebd9827bad2d1f0946fd62))


## v1.2.0 (2026-06-12)

### Features

- Implements cf accessor on Request
  ([`5777f80`](https://github.com/cloudflare/workers-py/commit/5777f80ead8d9a3c452fe3b6b8f2dc041d6c80d3))


## v1.1.6 (2026-05-28)

### Bug Fixes

- Include asgi.py in the wheel ([#110](https://github.com/cloudflare/workers-py/pull/110),
  [`cab6fab`](https://github.com/cloudflare/workers-py/commit/cab6fab48e63b05ac6d9b230c69657bde97eb0b8))


## v1.1.5 (2026-05-19)

### Bug Fixes

- Wrap DurableObject.abort() so that python cleanup can be done before abort
  ([#106](https://github.com/cloudflare/workers-py/pull/106),
  [`bf6acf2`](https://github.com/cloudflare/workers-py/commit/bf6acf24429fb1525f34334ff2cefffa45b287ef))

- **runtime-sdk**: Wrap DO.abort() to cleanup stale tasks before abortion
  ([#106](https://github.com/cloudflare/workers-py/pull/106),
  [`bf6acf2`](https://github.com/cloudflare/workers-py/commit/bf6acf24429fb1525f34334ff2cefffa45b287ef))


## v1.1.4 (2026-05-06)

### Bug Fixes

- Make pth file not warn when run in native Python
  ([#100](https://github.com/cloudflare/workers-py/pull/100),
  [`3c60df6`](https://github.com/cloudflare/workers-py/commit/3c60df6fd59c3ab65adeb5216feee3d52345ebb7))


## v1.1.3 (2026-05-04)

### Bug Fixes

- Add entropy import context for packages from workerd
  ([#99](https://github.com/cloudflare/workers-py/pull/99),
  [`6e574ca`](https://github.com/cloudflare/workers-py/commit/6e574ca000776645d3cf2883e515c96f49a43c2c))


## v1.1.2 (2026-04-21)

### Bug Fixes

- Make top level asgi import work with snapshots
  ([#93](https://github.com/cloudflare/workers-py/pull/93),
  [`3dd4115`](https://github.com/cloudflare/workers-py/commit/3dd41151d201aca4e1b895638fd3926eb1c68756))


## v1.1.1 (2026-03-18)

### Bug Fixes

- Fix Python ASGI adaptor to handle streaming responses correctly
  ([#82](https://github.com/cloudflare/workers-py/pull/82),
  [`d3ea87a`](https://github.com/cloudflare/workers-py/commit/d3ea87aff37c7a833f0602cc2a8018f1d5dde91b))

- Fix streaming responses in asgi module ([#82](https://github.com/cloudflare/workers-py/pull/82),
  [`d3ea87a`](https://github.com/cloudflare/workers-py/commit/d3ea87aff37c7a833f0602cc2a8018f1d5dde91b))


## v1.1.0 (2026-03-12)

### Features

- **workers-py**: Make workers cli install workers-runtime-sdk
  ([#74](https://github.com/cloudflare/workers-py/pull/74),
  [`a62f255`](https://github.com/cloudflare/workers-py/commit/a62f255e51555d212ecbb98f93e7145e251863f4))


## v1.0.2 (2026-03-12)

### Bug Fixes

- Fix types in workers-runtime-sdk ([#73](https://github.com/cloudflare/workers-py/pull/73),
  [`c46de58`](https://github.com/cloudflare/workers-py/commit/c46de58086d5f27341194fb48353bea7acc08312))


## v1.0.1 (2026-03-12)

### Bug Fixes

- Include correct files in wheel ([#71](https://github.com/cloudflare/workers-py/pull/71),
  [`b544b80`](https://github.com/cloudflare/workers-py/commit/b544b80423b249df41b58fb8f807cbee5ea170fb))


## v1.0.0 (2026-03-12)

- Initial Release
