from django.urls import path
from .views import (
    ProductListAPIView, ProductDetailAPIView, CategoryListAPIView, 
    SubCategoryListAPIView, ProductShareListCreateAPIView
)

urlpatterns = [
    path("", ProductListAPIView.as_view(), name="product_list_api"),
    path("product-shares/", ProductShareListCreateAPIView.as_view(), name="product_shares_api"),
    path("<uuid:id>/", ProductDetailAPIView.as_view(), name="product_detail_api"),
    path("categories/", CategoryListAPIView.as_view(), name="category_list_api"),
    path("subcategories/", SubCategoryListAPIView.as_view(), name="subcategory_list_api"),
]


