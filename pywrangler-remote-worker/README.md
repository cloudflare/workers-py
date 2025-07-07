# Pywrangler Remote Worker

This is a remote worker that uses pywrangler to gather a set of vendored packages
based on an input pyproject.toml file.

### Common commands

```
$ wrangler deploy
$ wrangler deploy
$ vitest
```

### Developing

A curl request that will return a vendor tarball:

```
$ curl -X POST --data-binary @/path/to/a/pyproject.toml http://localhost:8787 -o vendor.tar.gz
```

----

In case you want to use a symlink in your Docker build, you can use this workaround:

```
# https://stackoverflow.com/a/62915644
$ tar -ch . | docker build --network=host -t pywrangler-test -
```

This is useful if you want to override the pyodide-build used by pywrangler. You can symlink it,
then copy it over in the Dockerfile and `uv pip install -p ..` it.