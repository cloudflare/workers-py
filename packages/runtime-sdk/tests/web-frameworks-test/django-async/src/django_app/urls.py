from django.urls import include, path, re_path
from rest_framework.routers import DefaultRouter

from django_app import views

router = DefaultRouter()


urlpatterns = [
    path("hello/", views.hello, name="hello"),
    path("status/<int:code>/", views.status_code, name="status-code"),
    path("echo-method/", views.echo_method, name="echo-method"),
    path("echo-headers/", views.echo_headers, name="echo-headers"),
    path("echo-query/", views.echo_query, name="echo-query"),
    path("echo-body/", views.echo_body, name="echo-body"),
    path("echo-form/", views.echo_form, name="echo-form"),
    path("items/<int:id>/", views.item_detail, name="item-detail"),
    path("users/<str:name>/", views.user_detail, name="user-detail"),
    path("posts/<slug:slug>/", views.post_detail, name="post-detail"),
    path("uuids/<uuid:uid>/", views.uuid_detail, name="uuid-detail"),
    re_path(r"^archive/(?P<year>[0-9]{4})/$", views.archive_year, name="archive-year"),
    path("api/v1/", include(("django_app.api_urls", "api"), namespace="v1")),
    path("reverse-test/", views.reverse_test, name="reverse-test"),
    path("template/hello/", views.template_hello, name="template-hello"),
    path("template/context/", views.template_context, name="template-context"),
    path(
        "template/inheritance/", views.template_inheritance, name="template-inheritance"
    ),
    path("form/validate/", views.form_validate, name="form-validate"),
    path("form/process/", views.form_process, name="form-process"),
    path("trigger-404/", views.trigger_404, name="trigger-404"),
    path("trigger-403/", views.trigger_403, name="trigger-403"),
    path("trigger-400/", views.trigger_400, name="trigger-400"),
    path("trigger-500/", views.trigger_500, name="trigger-500"),
    path("session/set/", views.session_set, name="session-set"),
    path("session/get/", views.session_get, name="session-get"),
    path("session/flush/", views.session_flush, name="session-flush"),
    path("stream/async-gen/", views.stream_async_gen, name="stream-async-gen"),
    path("stream/sync-gen/", views.stream_sync_gen, name="stream-sync-gen"),
    path("csrf/form/", views.csrf_form, name="csrf-form"),
    path("csrf/exempt/", views.csrf_exempt_view, name="csrf-exempt"),
    path("cache/set/", views.cache_set, name="cache-set"),
    path("cache/get/", views.cache_get, name="cache-get"),
    path("cache/delete/", views.cache_delete, name="cache-delete"),
    path("cache/clear/", views.cache_clear, name="cache-clear"),
    path("signals/send/", views.signal_send, name="signal-send"),
    path("signals/robust/", views.signal_robust, name="signal-robust"),
    path("auth/login/", views.auth_login, name="auth-login"),
    path("auth/logout/", views.auth_logout, name="auth-logout"),
    path("auth/user/", views.auth_user, name="auth-user"),
    path("auth/protected/", views.auth_protected, name="auth-protected"),
    path("auth/permission/", views.auth_permission, name="auth-permission"),
    path("async/sync-to-async/", views.sync_to_async_view, name="sync-to-async"),
    path("async/async-iter/", views.async_iter_view, name="async-iter"),
    path("upload/single/", views.upload_single, name="upload-single"),
    path("upload/multiple/", views.upload_multiple, name="upload-multiple"),
    path("paginate/", views.paginate_view, name="paginate"),
    path("cbv/", views.AsyncCBV.as_view(), name="async-cbv"),
    path("drf/", include(router.urls)),
    path("drf/", include("django_app.drf_views")),
]


handler400 = "django_app.views.custom_handler400"
handler403 = "django_app.views.custom_handler403"
handler404 = "django_app.views.custom_handler404"
handler500 = "django_app.views.custom_handler500"
