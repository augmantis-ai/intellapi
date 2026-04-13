"""DRF router fixture covering ViewSets and @action endpoints."""

from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


class UserSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    email = serializers.EmailField(help_text="Email address")


class UserViewSet(viewsets.ViewSet):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def list(self, request):
        """List users."""
        return Response([])

    def retrieve(self, request, pk=None):
        """Retrieve a user."""
        return Response({"id": 1, "email": "user@example.com"})

    @action(detail=True, methods=["post"], url_path="reset-password")
    def reset_password(self, request, pk=None):
        """Reset a user's password."""
        return Response({"status": "ok"})
