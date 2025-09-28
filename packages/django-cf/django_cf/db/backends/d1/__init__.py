from django.core.exceptions import ImproperlyConfigured

from ...base_engine import CFDatabaseWrapper


class DatabaseWrapper(CFDatabaseWrapper):
    vendor = "cloudflare_d1"
    display_name = "D1"

    def get_connection_params(self):
        settings_dict = self.settings_dict
        if not settings_dict["CLOUDFLARE_BINDING"]:
            raise ImproperlyConfigured(
                "settings.DATABASES is improperly configured. "
                "Please supply the CLOUDFLARE_BINDING value."
            )
        kwargs = {
            "binding": settings_dict["CLOUDFLARE_BINDING"],
        }
        return kwargs
