from django.db.models import Q
from rest_framework import generics, permissions
from rest_framework_simplejwt.authentication import JWTAuthentication
from kiosks.authentication import KioskJWTAuthentication
from kiosks.models import KioskDevice
from .models import Product, Category
from .serializers import ProductSerializer, CategorySerializer


class ProductListAPIView(generics.ListCreateAPIView):
    """
    GET /api/products/
    GET /api/products/?kiosk_id=<uuid>
    GET /api/products/?device_id=<mac_or_serial>
    Returns list of active products with dynamic specifications and media assets.
    If authenticated as a kiosk device or filtered by kiosk_id / device_id,
    returns ONLY the products assigned to that kiosk for display.
    """
    serializer_class = ProductSerializer
    authentication_classes = [KioskJWTAuthentication, JWTAuthentication]
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        qs = Product.objects.select_related('category').prefetch_related('media_assets').filter(is_active=True).order_by('-created_at')
        
        # 1. Check if authenticated via Kiosk JWT Bearer token
        kiosk = getattr(self.request, 'kiosk', None)

        # 2. Check query parameters for kiosk_id or device_id
        kiosk_id = self.request.query_params.get('kiosk_id')
        device_id = self.request.query_params.get('device_id')

        if not kiosk and (kiosk_id or device_id):
            query = Q()
            if kiosk_id:
                query |= Q(id=kiosk_id)
            if device_id:
                query |= Q(device_id__iexact=device_id) | Q(serial_number__iexact=device_id)
            kiosk = KioskDevice.objects.filter(query).first()

        # If this request is for a specific kiosk device, return ONLY products assigned to that device
        if kiosk:
            return qs.filter(assigned_kiosks=kiosk).distinct()

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
