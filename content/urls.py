from django.urls import path
from .views import MediaLibraryListAPIView

urlpatterns = [
    path('', MediaLibraryListAPIView.as_view(), name='media_library_list'),
]
