# Compatibility module for existing code that imports `asgi` directly.
import sys

from workers import asgi as _asgi

sys.modules[__name__] = _asgi
