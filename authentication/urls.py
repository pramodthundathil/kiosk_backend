from django.urls import path 
from .import views 



urlpatterns = [

    # authentication usrls for kiosk admin and staff logins 
    path("", views.signin, name="signin"),
    path("signout", views.signout, name="signout")
    
]