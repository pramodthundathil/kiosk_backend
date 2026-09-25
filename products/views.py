from django.db.models import Q
from rest_framework import generics, permissions
from rest_framework_simplejwt.authentication import JWTAuthentication
from kiosks.authentication import KioskJWTAuthentication
from kiosks.models import KioskDevice
from .models import Product, Category, SubCategory
from .serializers import ProductSerializer, CategorySerializer, SubCategorySimpleSerializer, SubCategoryDetailSerializer


class ProductListAPIView(generics.ListCreateAPIView):
    """
    GET /api/products/
    GET /api/products/?kiosk_id=<uuid>
    GET /api/products/?device_id=<mac_or_serial>
    GET /api/products/?category_id=<uuid_or_code>
    GET /api/products/?sub_category_id=<uuid_or_code>
    Returns list of active products with dynamic specifications and media assets.
    If authenticated as a kiosk device or filtered by kiosk_id / device_id,
    returns ONLY the products assigned to that kiosk for display.
    """
    serializer_class = ProductSerializer
    authentication_classes = [KioskJWTAuthentication, JWTAuthentication]
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        qs = Product.objects.select_related(
            'category', 'sub_category', 'parent'
        ).prefetch_related(
            'media_assets', 'sub_products'
        ).filter(is_active=True).order_by('-created_at')
        
        # 1. Filter by Main Category (by ID or Code)
        category_param = self.request.query_params.get('category_id') or self.request.query_params.get('category')
        if category_param and category_param.lower() != 'all':
            qs = qs.filter(Q(category__id__iexact=category_param) | Q(category__code__iexact=category_param))

        # 2. Filter by Sub Category (by ID or Code)
        sub_cat_param = self.request.query_params.get('sub_category_id') or self.request.query_params.get('subcategory')
        if sub_cat_param and sub_cat_param.lower() != 'all':
            qs = qs.filter(Q(sub_category__id__iexact=sub_cat_param) | Q(sub_category__code__iexact=sub_cat_param))

        # 3. Check if authenticated via Kiosk JWT Bearer token
        kiosk = getattr(self.request, 'kiosk', None)

        # 4. Check query parameters for kiosk_id or device_id
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
    queryset = Product.objects.select_related(
        'category', 'sub_category', 'parent'
    ).prefetch_related(
        'media_assets', 'sub_products'
    ).filter(is_active=True)
    serializer_class = ProductSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = 'id'


class CategoryListAPIView(generics.ListCreateAPIView):
    """
    GET /api/categories/
    GET /api/products/categories/
    Returns active product categories with nested active subcategories.
    """
    queryset = Category.objects.filter(is_active=True).prefetch_related('subcategories').order_by('display_order', 'name')
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]


class SubCategoryListAPIView(generics.ListCreateAPIView):
    """
    GET /api/products/subcategories/
    GET /api/products/subcategories/?category_id=<uuid_or_code>
    Returns active subcategories, optionally filtered by category.
    """
    serializer_class = SubCategorySimpleSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        qs = SubCategory.objects.select_related('category').filter(is_active=True).order_by('display_order', 'name')
        category_param = self.request.query_params.get('category_id') or self.request.query_params.get('category')
        if category_param and category_param.lower() != 'all':
            qs = qs.filter(Q(category__id__iexact=category_param) | Q(category__code__iexact=category_param))
        return qs

