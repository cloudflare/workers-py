from django.urls import path
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response as DRFResponse
from rest_framework.versioning import QueryParameterVersioning
from rest_framework.views import APIView

from django_app.drf_auth import TokenAuthentication
from django_app.drf_throttling import TestAnonThrottle


class EchoAPIView(APIView):
    def get(self, request):
        return DRFResponse({"method": "GET", "query": request.query_params.dict()})

    def post(self, request):
        return DRFResponse(
            {"method": "POST", "data": request.data}, status=status.HTTP_201_CREATED
        )

    def put(self, request):
        return DRFResponse({"method": "PUT", "data": request.data})

    def delete(self, request):
        return DRFResponse({"method": "DELETE"}, status=status.HTTP_204_NO_CONTENT)


@api_view(["GET", "POST"])
def function_api_view(request):
    if request.method == "GET":
        return DRFResponse({"message": "hello from function view"})
    return DRFResponse({"received": request.data}, status=status.HTTP_201_CREATED)


class SerializerTestView(APIView):
    def post(self, request):
        from django_app.drf_serializers import ItemSerializer

        serializer = ItemSerializer(data=request.data)
        if serializer.is_valid():
            return DRFResponse({"valid": True, "data": serializer.validated_data})
        return DRFResponse(
            {"valid": False, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    def get(self, request):
        from django_app.drf_serializers import ItemSerializer

        data = {"name": "test-item", "price": 29.99, "quantity": 5, "tags": ["a", "b"]}
        serializer = ItemSerializer(data)
        return DRFResponse(serializer.data)


class NestedSerializerView(APIView):
    def post(self, request):
        from django_app.drf_serializers import OrderSerializer

        serializer = OrderSerializer(data=request.data)
        if serializer.is_valid():
            return DRFResponse({"valid": True, "data": serializer.validated_data})
        return DRFResponse(
            {"valid": False, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )


class AuthenticatedView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return DRFResponse({"user": str(request.user), "authenticated": True})


class AllowAnyView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return DRFResponse({"public": True})


class AdminOnlyView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAdminUser]

    def get(self, request):
        return DRFResponse({"admin": True})


class CustomAuthView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return DRFResponse({"user": request.user.username, "auth": "token"})


class ThrottledView(APIView):
    throttle_classes = [TestAnonThrottle]

    def get(self, request):
        return DRFResponse({"throttled": False})


class VersionedView(APIView):
    versioning_class = QueryParameterVersioning

    def get(self, request):
        return DRFResponse({"version": request.version or "default"})


class ContentNegotiationView(APIView):
    def post(self, request):
        data = request.data
        if hasattr(data, "dict"):
            data = data.dict()
        return DRFResponse({"content_type": request.content_type, "data": data})


urlpatterns = [
    path("api-view/", EchoAPIView.as_view(), name="drf-api-view"),
    path("function-view/", function_api_view, name="drf-function-view"),
    path("serializer/", SerializerTestView.as_view(), name="drf-serializer"),
    path("nested/", NestedSerializerView.as_view(), name="drf-nested"),
    path("auth/", AuthenticatedView.as_view(), name="drf-authenticated"),
    path("public/", AllowAnyView.as_view(), name="drf-public"),
    path("admin/", AdminOnlyView.as_view(), name="drf-admin"),
    path("custom-auth/", CustomAuthView.as_view(), name="drf-custom-auth"),
    path("versioned/", VersionedView.as_view(), name="drf-versioned"),
    path("throttled/", ThrottledView.as_view(), name="drf-throttled"),
    path("content/", ContentNegotiationView.as_view(), name="drf-content"),
]
