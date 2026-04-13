"""Sample Django REST views for extractor tests."""

from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


class UserSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(help_text="Full name")
    email = serializers.EmailField(help_text="Email address")


@api_view(["GET"])
def health(request):
    """Health endpoint."""
    return Response({"status": "ok"})


class UserListView(APIView):
    """Manage users."""

    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """List users."""
        return Response([])

    def post(self, request):
        """Create a user."""
        return Response({"id": 1, "name": "Alice", "email": "alice@example.com"})
