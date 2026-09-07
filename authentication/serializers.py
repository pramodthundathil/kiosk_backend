from rest_framework import serializers
from django.contrib.auth import authenticate, get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
from .models import User



class CMSLoginSerializer(serializers.Serializer):
    username = serializers.CharField(required=True)
    password = serializers.CharField(required=True, write_only=True)

    def validate(self, attrs):
        username = attrs.get('username')
        password = attrs.get('password')

        user = authenticate(username=username, password=password)
        if not user:
            raise serializers.ValidationError("Invalid credentials.")
        if not user.is_active:
            raise serializers.ValidationError("User account is disabled.")

        attrs['user'] = user
        return attrs

def issue_cms_jwt_tokens(user: User) -> dict:
    """Generates JWT access and refresh tokens tagged with token_category='cms'."""
    refresh = RefreshToken.for_user(user)
    refresh["token_category"] = "cms"
    refresh["role"] = user.role
    refresh["username"] = user.username

    access = refresh.access_token
    access["token_category"] = "cms"
    access["role"] = user.role
    access["username"] = user.username

    return {
        "access": str(access),
        "refresh": str(refresh),
        "username": user.username,
        "role": user.role,
        "role_display": user.get_role_display(),
    }
