from rest_framework.throttling import SimpleRateThrottle


class TestAnonThrottle(SimpleRateThrottle):
    scope = "test_anon"
    rate = "3/min"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }
