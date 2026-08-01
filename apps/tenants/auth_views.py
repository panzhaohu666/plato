"""Auth API: register + login with JWT tokens."""
from django.contrib.auth import authenticate
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from apps.tenants.models import User


@api_view(["POST"])
@permission_classes([AllowAny])
def register(request):
    """Register a new user and return JWT tokens."""
    username = request.data.get("username", "").strip()
    password = request.data.get("password", "").strip()

    if not username or not password:
        return Response({"error": "username and password required"}, status=400)

    if User.objects.filter(username=username).exists():
        return Response({"error": "username already taken"}, status=409)

    user = User.objects.create_user(username=username, password=password)
    refresh = RefreshToken.for_user(user)

    return Response({
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "user": {"id": user.pk, "username": user.username},
    }, status=201)


@api_view(["POST"])
@permission_classes([AllowAny])
def login(request):
    """Login and return JWT tokens."""
    username = request.data.get("username", "").strip()
    password = request.data.get("password", "").strip()

    user = authenticate(username=username, password=password)
    if user is None:
        return Response({"error": "invalid credentials"}, status=401)

    refresh = RefreshToken.for_user(user)

    return Response({
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "user": {"id": user.pk, "username": user.username},
    })


@api_view(["POST"])
@permission_classes([AllowAny])
def token_refresh(request):
    """Refresh an expired access token."""
    refresh_token = request.data.get("refresh", "")
    try:
        refresh = RefreshToken(refresh_token)
        return Response({"access": str(refresh.access_token)})
    except Exception:
        return Response({"error": "invalid refresh token"}, status=401)
