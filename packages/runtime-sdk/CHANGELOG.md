# CHANGELOG

<!-- version list -->

## v1.8.1 (2026-08-28)

### Bug Fixes

- Make Headers subclass Mapping ([#233](https://github.com/cloudflare/workers-py/pull/233),
  [`2e0a47f`](https://github.com/cloudflare/workers-py/commit/2e0a47f7aca2091a0396fcd8b04c03979326698a))


## v1.8.0 (2026-08-28)

### Bug Fixes

- Defer ASGI lifespan shutdown until request completion
  ([`3249184`](https://github.com/cloudflare/workers-py/commit/324918442748a0b87affc6128315ceb190e1b368))

- Make wsgi streaming response handlers async
  ([#191](https://github.com/cloudflare/workers-py/pull/191),
  [`12168ae`](https://github.com/cloudflare/workers-py/commit/12168aef7599067a910a518f1ce7860a00ae9a58))

- **runtime-sdk**: Close the WebSocket transport when the app task ends
  ([#166](https://github.com/cloudflare/workers-py/pull/166),
  [`e67e7e7`](https://github.com/cloudflare/workers-py/commit/e67e7e78af7fa6976f1f9966508b9869a6840ce5))

### Features

- Add wsgi.entrypoint like asgi.entrypoint
  ([#232](https://github.com/cloudflare/workers-py/pull/232),
  [`e044561`](https://github.com/cloudflare/workers-py/commit/e04456174b3f5bc9df8b3f8293ced6d08aaffc0f))


## v1.7.0 (2026-08-24)

### Bug Fixes

- Fixes Request body being released too early
  ([`84a20ac`](https://github.com/cloudflare/workers-py/commit/84a20acbfa28ea82fb69b2c279a56d9e25fd9639))

### Features

- Asgi.entrypoint syntax sugar for nicer asgi apps
  ([`5399270`](https://github.com/cloudflare/workers-py/commit/539927085a79e2d88a287cc70ccfa433ec257e1d))


## v1.6.15 (2026-08-21)

### Bug Fixes

- Handle ASGI WebSocket close events and environment propagation
  ([`47cc488`](https://github.com/cloudflare/workers-py/commit/47cc488e2bad1c9f3030a16d73301b80fca90f5c))


## v1.6.14 (2026-08-19)

### Bug Fixes

- Fixes fastapi lifespan state not persisting
  ([`fadd19b`](https://github.com/cloudflare/workers-py/commit/fadd19bcb6ca47518d5e42562879164dd62ab404))


## v1.6.13 (2026-08-12)

### Bug Fixes

- **runtime-sdk**: Preserve repeated response headers (multiple `Set-Cookie`)
  ([#167](https://github.com/cloudflare/workers-py/pull/167),
  [`f68bf6d`](https://github.com/cloudflare/workers-py/commit/f68bf6d622c896b6c61fe3c615d43d6e9b05d19b))


## v1.6.12 (2026-08-11)

### Bug Fixes

- **runtime-sdk**: Send empty WebSocket frames instead of dropping them
  ([#165](https://github.com/cloudflare/workers-py/pull/165),
  [`a4128ce`](https://github.com/cloudflare/workers-py/commit/a4128cee402aa6f28f01e3e2268241d05d9fd393))


## v1.6.11 (2026-08-10)

### Bug Fixes

- Implements tests for FastAPI StaticFiles and anyio thread patch
  ([`a30f53e`](https://github.com/cloudflare/workers-py/commit/a30f53e95edcf42fc93e5e2dc84251121881418b))


## v1.6.10 (2026-08-10)

### Bug Fixes

- **runtime-sdk**: Terminate the response stream when the app fails mid-stream
  ([#168](https://github.com/cloudflare/workers-py/pull/168),
  [`fd4dde9`](https://github.com/cloudflare/workers-py/commit/fd4dde98fcc39f405a7cf320a6db49a83426f46b))


## v1.6.9 (2026-08-10)

### Bug Fixes

- **runtime-sdk**: Deliver binary WebSocket frames as ASGI `bytes`
  ([#164](https://github.com/cloudflare/workers-py/pull/164),
  [`44ca368`](https://github.com/cloudflare/workers-py/commit/44ca36818367af23ffd0c76f5d2dc7588219b340))


## v1.6.8 (2026-08-05)

### Bug Fixes

- **runtime-sdk**: Do not include HTTP body for null body status codes
  ([#162](https://github.com/cloudflare/workers-py/pull/162),
  [`693d594`](https://github.com/cloudflare/workers-py/commit/693d5945fd6531beb0d9d2fd3c97bf7ee2c8f1f3))


## v1.6.7 (2026-08-05)

### Bug Fixes

- Fix entropy patch for newer pydantic versions
  ([#153](https://github.com/cloudflare/workers-py/pull/153),
  [`81a4b6b`](https://github.com/cloudflare/workers-py/commit/81a4b6bad37373e0b448dd2dbedbf6cec0f47b8c))


## v1.6.6 (2026-08-03)

### Bug Fixes

- **runtime-sdk**: Percent-decode `scope["path"]` per the ASGI spec
  ([#169](https://github.com/cloudflare/workers-py/pull/169),
  [`2138e44`](https://github.com/cloudflare/workers-py/commit/2138e44dc0bc419a1227497576154346da3ea522))

- **runtime-sdk**: Percent-decode scope["path"] per the ASGI spec
  ([#169](https://github.com/cloudflare/workers-py/pull/169),
  [`2138e44`](https://github.com/cloudflare/workers-py/commit/2138e44dc0bc419a1227497576154346da3ea522))


## v1.6.5 (2026-08-03)

### Bug Fixes

- Fix function object returned from RPC to be a callable
  ([#160](https://github.com/cloudflare/workers-py/pull/160),
  [`1019d7e`](https://github.com/cloudflare/workers-py/commit/1019d7e74d824db38328a0a25a7bf09956a7f961))


## v1.6.4 (2026-07-30)

### Bug Fixes

- **runtime-sdk**: Deliver client WebSocket close events to the ASGI app
  ([#158](https://github.com/cloudflare/workers-py/pull/158),
  [`6f53155`](https://github.com/cloudflare/workers-py/commit/6f53155b5620137c749a64dc4ee785505cede74e))

- **runtime-sdk**: Register the WebSocket close handler on onclose
  ([#158](https://github.com/cloudflare/workers-py/pull/158),
  [`6f53155`](https://github.com/cloudflare/workers-py/commit/6f53155b5620137c749a64dc4ee785505cede74e))

- **runtime-sdk**: Surface client closes as websocket.disconnect
  ([#158](https://github.com/cloudflare/workers-py/pull/158),
  [`6f53155`](https://github.com/cloudflare/workers-py/commit/6f53155b5620137c749a64dc4ee785505cede74e))


## v1.6.3 (2026-07-17)

### Bug Fixes

- Wrap AnalyticsEngine, which is used in production
  ([#155](https://github.com/cloudflare/workers-py/pull/155),
  [`91e4e50`](https://github.com/cloudflare/workers-py/commit/91e4e500ddfe849cae0bd75481e0e62ff01de97d))


## v1.6.2 (2026-07-09)

### Bug Fixes

- Uuid_utils is a Rust package needs rust package import context
  ([#151](https://github.com/cloudflare/workers-py/pull/151),
  [`61e91f3`](https://github.com/cloudflare/workers-py/commit/61e91f3b3cffc26fef411c67d018b7d5728df3c4))


## v1.6.1 (2026-07-09)

### Bug Fixes

- Improve lifespan handling in asgi.py ([#148](https://github.com/cloudflare/workers-py/pull/148),
  [`7c9adfc`](https://github.com/cloudflare/workers-py/commit/7c9adfce6c3997f1547901755e97c685ef6e6be3))


## v1.6.0 (2026-07-08)

### Features

- Add wsgi.py analogous to asgi.py ([#145](https://github.com/cloudflare/workers-py/pull/145),
  [`247f9ff`](https://github.com/cloudflare/workers-py/commit/247f9ff5387eb2d286c65c1199f3ff51938578fa))


## v1.5.4 (2026-07-08)

### Bug Fixes

- Relax required-python version to support Python 3.11
  ([#149](https://github.com/cloudflare/workers-py/pull/149),
  [`31d0f69`](https://github.com/cloudflare/workers-py/commit/31d0f696b2f64daf27ef629242957dff96bdde81))


## v1.5.3 (2026-07-03)

### Bug Fixes

- Update Workflows wrapper to work more natively with Python objects
  ([#138](https://github.com/cloudflare/workers-py/pull/138),
  [`63ea6a0`](https://github.com/cloudflare/workers-py/commit/63ea6a0842875e04f3883bd050a097a3ef7152bd))


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
