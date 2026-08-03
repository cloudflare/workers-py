import hashlib

from django.contrib.auth.backends import BaseBackend

USERS = {
    "testuser": {"pk": 1, "password": "testpass123", "is_staff": False},
    "admin": {"pk": 2, "password": "adminpass123", "is_staff": True},
}

_USERNAME_BY_PK = {data["pk"]: username for username, data in USERS.items()}


class _PkField:
    def value_to_string(self, obj):
        return str(obj.pk)


class _Meta:
    pk = _PkField()


class InMemoryUser:
    _meta = _Meta()
    last_login = None

    def __init__(self, username):
        data = USERS[username]
        self.username = username
        self.pk = data["pk"]
        self.id = data["pk"]
        self.is_staff = data["is_staff"]
        self.is_authenticated = True
        self.is_anonymous = False
        self.is_active = True

    def save(self, *args, **kwargs):
        pass

    def __str__(self):
        return self.username

    def get_username(self):
        return self.username

    def get_session_auth_hash(self):
        return hashlib.sha256(self.username.encode()).hexdigest()

    def has_perm(self, perm, obj=None):
        return self.is_staff or perm == "can_view"

    async def ahas_perm(self, perm, obj=None):
        return self.has_perm(perm, obj=obj)

    def has_perms(self, perm_list, obj=None):
        return all(self.has_perm(perm, obj=obj) for perm in perm_list)

    async def ahas_perms(self, perm_list, obj=None):
        return self.has_perms(perm_list, obj=obj)

    def has_module_perms(self, app_label):
        return self.is_staff


class InMemoryBackend(BaseBackend):
    def authenticate(self, request, username=None, password=None):
        if username is None or password is None:
            return None
        data = USERS.get(username)
        if data is None or data["password"] != password:
            return None
        return InMemoryUser(username)

    def get_user(self, user_id):
        username = _USERNAME_BY_PK.get(user_id)
        if username is None:
            return None
        return InMemoryUser(username)
