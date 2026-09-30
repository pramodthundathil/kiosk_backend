import uuid
from django.db.models import Q
from rest_framework import generics, permissions
from rest_framework_simplejwt.authentication import JWTAuthentication
from kiosks.authentication import KioskJWTAuthentication
from kiosks.models import KioskDevice
from .models import Product, Category, SubCategory, ProductShare
from .serializers import (
    ProductSerializer, CategorySerializer, SubCategorySimpleSerializer, 
    SubCategoryDetailSerializer, ProductShareSerializer
)



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
            'media_assets', 'child_variants'
        ).filter(is_active=True, parent__isnull=True).order_by('-created_at')
        
        # 1. Filter by Main Category (by ID or Code)
        category_param = self.request.query_params.get('category_id') or self.request.query_params.get('category')
        if category_param and category_param.lower() != 'all':
            try:
                cat_uuid = uuid.UUID(category_param)
                qs = qs.filter(
                    Q(category__id=cat_uuid) |
                    Q(category__code__iexact=category_param) |
                    Q(sub_category__category__id=cat_uuid) |
                    Q(sub_category__category__code__iexact=category_param)
                )
            except (ValueError, TypeError):
                qs = qs.filter(
                    Q(category__code__iexact=category_param) |
                    Q(sub_category__category__code__iexact=category_param)
                )

        # 2. Filter by Sub Category (by ID or Code)
        sub_cat_param = self.request.query_params.get('sub_category_id') or self.request.query_params.get('subcategory')
        if sub_cat_param and sub_cat_param.lower() != 'all':
            try:
                sub_uuid = uuid.UUID(sub_cat_param)
                qs = qs.filter(Q(sub_category__id=sub_uuid) | Q(sub_category__code__iexact=sub_cat_param))
            except (ValueError, TypeError):
                qs = qs.filter(sub_category__code__iexact=sub_cat_param)

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

        if kiosk:
            assigned_ids = kiosk.assigned_products.values_list('id', flat=True)
            parent_ids = Product.objects.filter(
                id__in=assigned_ids, parent__isnull=False
            ).values_list('parent_id', flat=True)
            all_ids = list(set(list(assigned_ids) + list(parent_ids)))
            return qs.filter(id__in=all_ids).distinct()

        return qs


class ProductDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET /api/products/<id>/
    Returns single product details with dynamic specifications and media assets.
    """
    queryset = Product.objects.select_related(
        'category', 'sub_category', 'parent'
    ).prefetch_related(
        'media_assets', 'child_variants'
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
            try:
                cat_uuid = uuid.UUID(category_param)
                qs = qs.filter(Q(category__id=cat_uuid) | Q(category__code__iexact=category_param))
            except (ValueError, TypeError):
                qs = qs.filter(category__code__iexact=category_param)
        return qs


class ProductShareListCreateAPIView(generics.ListCreateAPIView):
    """
    GET /api/products/product-shares/
    POST /api/products/product-shares/
    Logs product sharing activity from Staff App.
    """
    queryset = ProductShare.objects.select_related('staff_user', 'product', 'variant').all().order_by('-created_at')
    serializer_class = ProductShareSerializer
    permission_classes = [permissions.AllowAny]

    def perform_create(self, serializer):
        user = self.request.user if (self.request.user and self.request.user.is_authenticated) else None
        serializer.save(staff_user=user)



