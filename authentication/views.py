from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages  

def signin(request):
    if request.user.is_authenticated:
        return redirect('admin_dashboard')

    if request.method == "POST":
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            if not user.is_active:
                messages.error(request, "Your account has been disabled. Please contact an administrator.")
                return redirect('signin')

            login(request, user)
            messages.success(request, f"Welcome back, {user.username}!")
            return redirect('admin_dashboard')
        else:
            messages.error(request, "Invalid username or password. Please try again.")
            return redirect('signin')

    return render(request, "admin/signin.html")


def signout(request):
    logout(request)
    messages.info(request, "You have been logged out successfully.")
    return redirect('signin')


from rest_framework import views, status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from .serializers import CMSLoginSerializer, issue_cms_jwt_tokens

class CMSAuthLoginView(views.APIView):
    """
    POST /api/cms/auth/login/
    Authenticates CMS Users (Super Admin, Admin, Managers) and returns CMS JWT access & refresh tokens.
    """
    permission_classes = [AllowAny]
    serializer_class = CMSLoginSerializer

    def post(self, request):
        serializer = CMSLoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = serializer.validated_data['user']
        tokens = issue_cms_jwt_tokens(user)
        return Response(tokens, status=status.HTTP_200_OK)

