import json

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, permission_required
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.core.paginator import Paginator
from django.dispatch import Signal
from django.http import Http404, HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.html import escape
from django.views import View
from django.views.decorators.csrf import (
    csrf_exempt,
    csrf_protect,
    ensure_csrf_cookie,
)

from django_app.forms import ContactForm

custom_signal = Signal()
signal_events = []


def signal_receiver(sender, **kwargs):
    data = kwargs.get("data")
    signal_events.append(data)
    return data


custom_signal.connect(signal_receiver, dispatch_uid="django_app_signal_receiver")


def _json_body(request):
    if not request.body:
        return {}
    return json.loads(request.body.decode())


def hello(request):
    return HttpResponse("hello")


def status_code(request, code):
    return HttpResponse(f"status {escape(str(code))}", status=code)


def echo_method(request):
    return JsonResponse({"method": request.method})


def echo_headers(request):
    return JsonResponse({k.lower(): v for k, v in request.headers.items()})


def echo_query(request):
    return JsonResponse(request.GET.dict())


def echo_body(request):
    return JsonResponse(_json_body(request))


def echo_form(request):
    return JsonResponse(request.POST.dict())


def item_detail(request, id):
    return JsonResponse({"id": id, "type": type(id).__name__})


def user_detail(request, name):
    return JsonResponse({"name": name})


def post_detail(request, slug):
    return JsonResponse({"slug": slug})


def uuid_detail(request, uid):
    return JsonResponse({"uuid": str(uid)})


def archive_year(request, year):
    return JsonResponse({"year": year})


def reverse_test(request):
    return HttpResponse(reverse("hello"))


def template_hello(request):
    return render(request, "hello.html", {"name": "World"})


def template_context(request):
    return render(
        request,
        "context_test.html",
        {"items": [1, 2, 3], "show_items": True, "greeting": "hello"},
    )


def template_inheritance(request):
    return render(request, "base.html")


def form_validate(request):
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            return JsonResponse({"valid": True, "data": form.cleaned_data})
        return JsonResponse({"valid": False, "errors": form.errors.get_json_data()})
    form = ContactForm()
    return HttpResponse(f"<form>{form.as_div()}</form>")


def form_process(request):
    form = ContactForm(request.POST or None)
    valid = form.is_valid() if request.method == "POST" else False
    return JsonResponse(
        {
            "valid": valid,
            "data": form.cleaned_data if valid else None,
            "errors": None
            if valid
            else form.errors.get_json_data()
            if request.method == "POST"
            else None,
        }
    )


def trigger_404(request):
    raise Http404("not found")


def trigger_403(request):
    raise PermissionDenied("forbidden")


def trigger_400(request):
    raise SuspiciousOperation("bad request")


def trigger_500(request):
    raise RuntimeError("server error")


def custom_handler400(request, exception):
    return JsonResponse({"error": "bad_request", "detail": str(exception)}, status=400)


def custom_handler403(request, exception):
    return JsonResponse({"error": "forbidden", "detail": str(exception)}, status=403)


def custom_handler404(request, exception):
    return JsonResponse({"error": "not_found", "detail": str(exception)}, status=404)


def custom_handler500(request):
    return JsonResponse({"error": "server_error"}, status=500)


def session_set(request):
    payload = _json_body(request)
    for key, value in payload.items():
        request.session[key] = value
    return JsonResponse({"set": list(payload.keys())})


def session_get(request):
    return JsonResponse(dict(request.session.items()))


def session_flush(request):
    request.session.flush()
    return JsonResponse({"flushed": True})


def _sync_stream():
    for index in range(5):
        yield f"chunk-{index}\n"


def stream_sync_gen(request):
    return StreamingHttpResponse(_sync_stream(), content_type="text/plain")


@csrf_protect
@ensure_csrf_cookie
def csrf_form(request):
    if request.method == "POST":
        return JsonResponse({"csrf": "ok"})
    return render(request, "csrf_form.html")


@csrf_exempt
def csrf_exempt_view(request):
    return JsonResponse({"csrf_exempt": True})


def cache_set(request):
    payload = _json_body(request)
    key = payload.get("key")
    value = payload.get("value")
    cache.set(key, value)
    return JsonResponse({"cached": True, "key": key, "value": value})


def cache_get(request):
    key = request.GET.get("key")
    value = cache.get(key)
    return JsonResponse({"key": key, "value": value})


def cache_delete(request):
    key = request.GET.get("key")
    cache.delete(key)
    return JsonResponse({"deleted": True, "key": key})


def cache_clear(request):
    cache.clear()
    return JsonResponse({"cleared": True})


def signal_send(request):
    signal_events.clear()
    custom_signal.send(sender=None, data="test")
    return JsonResponse({"sent": True, "received": list(signal_events)})


def signal_robust(request):
    signal_events.clear()
    responses = custom_signal.send_robust(sender=None, data="test")
    results = []
    for receiver, response in responses:
        results.append(
            {
                "receiver": getattr(receiver, "__name__", receiver.__class__.__name__),
                "response": str(response),
            }
        )
    return JsonResponse({"sent": True, "results": results})


def auth_login(request):
    payload = _json_body(request)
    user = authenticate(
        request,
        username=payload.get("username"),
        password=payload.get("password"),
    )
    if user is None:
        return JsonResponse({"authenticated": False})
    login(request, user, backend="django_app.auth_backend.InMemoryBackend")
    return JsonResponse({"authenticated": True})


def auth_logout(request):
    logout(request)
    return JsonResponse({"logged_out": True})


def auth_user(request):
    user = request.user
    return JsonResponse(
        {
            "is_authenticated": user.is_authenticated,
            "username": getattr(user, "username", ""),
        }
    )


@login_required
def auth_protected(request):
    user = request.user
    return JsonResponse({"protected": True, "user": user.username})


@permission_required("can_view")
def auth_permission(request):
    return JsonResponse({"permission": True})


def upload_single(request):
    uploaded_file = request.FILES["file"]
    return JsonResponse(
        {
            "name": uploaded_file.name,
            "size": uploaded_file.size,
            "content": uploaded_file.read().decode(),
        }
    )


def upload_multiple(request):
    files = [{"name": f.name, "size": f.size} for f in request.FILES.getlist("file")]
    return JsonResponse({"files": files})


def paginate_view(request):
    items = list(range(1, 51))
    paginator = Paginator(items, 10)
    page = paginator.get_page(request.GET.get("page", 1))
    return JsonResponse(
        {
            "page": page.number,
            "items": list(page.object_list),
            "num_pages": paginator.num_pages,
            "has_next": page.has_next(),
            "has_previous": page.has_previous(),
        }
    )


class SyncCBV(View):
    def get(self, request):
        return JsonResponse({"method": "GET"})

    def post(self, request):
        return JsonResponse({"method": "POST"})

    def put(self, request):
        return JsonResponse({"method": "PUT"})

    def delete(self, request):
        return JsonResponse({"method": "DELETE"})

    def patch(self, request):
        return JsonResponse({"method": "PATCH"})
