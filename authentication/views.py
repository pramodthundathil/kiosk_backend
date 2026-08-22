from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages  

def signin(request):
    if request.method  == "POST":
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            if user.is_kiosk:
                messages.error(request, "You are not authorized to view this page.")
                logout(request)
                return redirect('signin')
            elif user.is_admin_role:
                messages.info(request, "You are logged in as an admin.")
                return redirect('admin_dashboard')
            elif user.is_staff_role:
                messages.info(request, "You are logged in as staff.")
                return redirect('admin_dashboard')
            else:
                messages.error(request, "Your account has an invalid role configuration.")
                logout(request)
                return redirect('signin')
        else:
            messages.error(request, "Invalid username or password. Please try again.")
            return redirect('signin')

    return render(request, "admin/signin.html")


def signout(request):
    logout(request)
    return redirect('signin')

