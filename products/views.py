from rest_framework import generics, permissions
from .models import Product, Category
from .serializers import ProductSerializer, CategorySerializer


class ProductListAPIView(generics.ListCreateAPIView):
    """
    GET /api/products/
    GET /api/products/?kiosk_id=<uuid>
    Returns list of active products with dynamic specifications and media assets.
    If filtered by kiosk_id, returns products assigned to that kiosk.
    """
    serializer_class = ProductSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        qs = Product.objects.select_related('category').prefetch_related('media_assets').filter(is_active=True).order_by('-created_at')
        kiosk_id = self.request.query_params.get('kiosk_id')
        if not kiosk_id and hasattr(self.request, 'kiosk') and self.request.kiosk:
            kiosk_id = self.request.kiosk.id

        if kiosk_id:
            assigned = qs.filter(assigned_kiosks__id=kiosk_id)
            if assigned.exists():
                return assigned
        return qs


class ProductDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET /api/products/<id>/
    Returns single product details with dynamic specifications and media assets.
    """
    queryset = Product.objects.select_related('category').prefetch_related('media_assets').filter(is_active=True)
    serializer_class = ProductSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = 'id'


class CategoryListAPIView(generics.ListCreateAPIView):
    """
    GET /api/categories/
    Returns product categories.
    """
    queryset = Category.objects.filter(is_active=True).order_by('name')
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]
