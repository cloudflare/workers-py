import json

from asgiref.sync import sync_to_async
from django.contrib.auth import aauthenticate, alogin, alogout
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


async def hello(request):
    return HttpResponse("hello")


async def status_code(request, code):
    return HttpResponse(f"status {escape(str(code))}", status=code)


async def echo_method(request):
    return JsonResponse({"method": request.method})


async def echo_headers(request):
    return JsonResponse({k.lower(): v for k, v in request.headers.items()})


async def echo_query(request):
    return JsonResponse(request.GET.dict())


async def echo_body(request):
    return JsonResponse(_json_body(request))


async def echo_form(request):
    return JsonResponse(request.POST.dict())


async def item_detail(request, id):
    return JsonResponse({"id": id, "type": type(id).__name__})


async def user_detail(request, name):
    return JsonResponse({"name": name})


async def post_detail(request, slug):
    return JsonResponse({"slug": slug})


async def uuid_detail(request, uid):
    return JsonResponse({"uuid": str(uid)})


async def archive_year(request, year):
    return JsonResponse({"year": year})


async def reverse_test(request):
    return HttpResponse(reverse("hello"))


async def template_hello(request):
    return render(request, "hello.html", {"name": "World"})


async def template_context(request):
    return render(
        request,
        "context_test.html",
        {"items": [1, 2, 3], "show_items": True, "greeting": "hello"},
    )


async def template_inheritance(request):
    return render(request, "base.html")


async def form_validate(request):
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            return JsonResponse({"valid": True, "data": form.cleaned_data})
        return JsonResponse({"valid": False, "errors": form.errors.get_json_data()})
    form = ContactForm()
    return HttpResponse(f"<form>{form.as_div()}</form>")


async def form_process(request):
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


async def trigger_404(request):
    raise Http404("not found")


async def trigger_403(request):
    raise PermissionDenied("forbidden")


async def trigger_400(request):
    raise SuspiciousOperation("bad request")


async def trigger_500(request):
    raise RuntimeError("server error")


def custom_handler400(request, exception):
    return JsonResponse({"error": "bad_request", "detail": str(exception)}, status=400)


def custom_handler403(request, exception):
    return JsonResponse({"error": "forbidden", "detail": str(exception)}, status=403)


def custom_handler404(request, exception):
    return JsonResponse({"error": "not_found", "detail": str(exception)}, status=404)


def custom_handler500(request):
    return JsonResponse({"error": "server_error"}, status=500)


async def session_set(request):
    payload = _json_body(request)
    for key, value in payload.items():
        request.session[key] = value
    return JsonResponse({"set": list(payload.keys())})


async def session_get(request):
    return JsonResponse(dict(request.session.items()))


async def session_flush(request):
    await request.session.aflush()
    return JsonResponse({"flushed": True})


async def _async_stream():
    for index in range(5):
        yield f"chunk-{index}\n"


def _sync_stream():
    for index in range(5):
        yield f"chunk-{index}\n"


async def stream_async_gen(request):
    return StreamingHttpResponse(_async_stream(), content_type="text/plain")


async def stream_sync_gen(request):
    return StreamingHttpResponse(_sync_stream(), content_type="text/plain")


@csrf_protect
@ensure_csrf_cookie
async def csrf_form(request):
    if request.method == "POST":
        return JsonResponse({"csrf": "ok"})
    return render(request, "csrf_form.html")


@csrf_exempt
async def csrf_exempt_view(request):
    return JsonResponse({"csrf_exempt": True})


async def cache_set(request):
    payload = _json_body(request)
    key = payload.get("key")
    value = payload.get("value")
    await cache.aset(key, value)
    return JsonResponse({"cached": True, "key": key, "value": value})


async def cache_get(request):
    key = request.GET.get("key")
    value = await cache.aget(key)
    return JsonResponse({"key": key, "value": value})


async def cache_delete(request):
    key = request.GET.get("key")
    await cache.adelete(key)
    return JsonResponse({"deleted": True, "key": key})


async def cache_clear(request):
    await cache.aclear()
    return JsonResponse({"cleared": True})


async def signal_send(request):
    signal_events.clear()
    await custom_signal.asend(sender=None, data="test")
    return JsonResponse({"sent": True, "received": list(signal_events)})


async def signal_robust(request):
    signal_events.clear()
    responses = await custom_signal.asend_robust(sender=None, data="test")
    results = []
    for receiver, response in responses:
        results.append(
            {
                "receiver": getattr(receiver, "__name__", receiver.__class__.__name__),
                "response": str(response),
            }
        )
    return JsonResponse({"sent": True, "results": results})


async def auth_login(request):
    payload = _json_body(request)
    user = await aauthenticate(
        request,
        username=payload.get("username"),
        password=payload.get("password"),
    )
    if user is None:
        return JsonResponse({"authenticated": False})
    await alogin(request, user, backend="django_app.auth_backend.InMemoryBackend")
    return JsonResponse({"authenticated": True})


async def auth_logout(request):
    await alogout(request)
    return JsonResponse({"logged_out": True})


async def auth_user(request):
    user = await request.auser()
    return JsonResponse(
        {
            "is_authenticated": user.is_authenticated,
            "username": getattr(user, "username", ""),
        }
    )


@login_required
async def auth_protected(request):
    user = await request.auser()
    return JsonResponse({"protected": True, "user": user.username})


@permission_required("can_view")
async def auth_permission(request):
    return JsonResponse({"permission": True})


def _sync_utility():
    return "sync result"


async def sync_to_async_view(request):
    result = await sync_to_async(_sync_utility)()
    return JsonResponse({"result": result})


async def _async_numbers():
    for value in range(5):
        yield value


async def async_iter_view(request):
    items = [value async for value in _async_numbers()]
    return JsonResponse({"items": items})


async def upload_single(request):
    uploaded_file = request.FILES["file"]
    return JsonResponse(
        {
            "name": uploaded_file.name,
            "size": uploaded_file.size,
            "content": uploaded_file.read().decode(),
        }
    )


async def upload_multiple(request):
    files = [{"name": f.name, "size": f.size} for f in request.FILES.getlist("file")]
    return JsonResponse({"files": files})


async def paginate_view(request):
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


class AsyncCBV(View):
    async def get(self, request):
        return JsonResponse({"method": "GET"})

    async def post(self, request):
        return JsonResponse({"method": "POST"})

    async def put(self, request):
        return JsonResponse({"method": "PUT"})

    async def delete(self, request):
        return JsonResponse({"method": "DELETE"})

    async def patch(self, request):
        return JsonResponse({"method": "PATCH"})
