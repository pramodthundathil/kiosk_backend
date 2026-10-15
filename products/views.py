import uuid
import urllib.parse
from django.db.models import Q
from django.shortcuts import render, get_object_or_404, redirect
from django.http import Http404
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from rest_framework import generics, permissions
from rest_framework_simplejwt.authentication import JWTAuthentication
from kiosks.authentication import KioskJWTAuthentication
from kiosks.models import KioskDevice
from .models import Product, Category, SubCategory, ProductShare
from content.models import MediaAsset
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


# ==========================================
# PUBLIC PRODUCT VIEWS (Web & Mobile Responsive)
# ==========================================

def public_product_detail(request, identifier):
    """
    Public web view to display full product details, interactive 3D model, videos,
    specifications, features, testing certifications, and download materials.
    Accessible without authentication on mobile and desktop web browsers.
    Supports lookup by Product UUID or SKU code.
    """
    product = None
    identifier_str = str(identifier).strip()

    # 1. Try UUID lookup
    try:
        val_uuid = uuid.UUID(identifier_str)
        product = Product.objects.select_related(
            'category', 'sub_category', 'parent'
        ).prefetch_related(
            'media_assets', 'child_variants', 'child_variants__media_assets'
        ).filter(id=val_uuid, is_active=True).first()
    except (ValueError, AttributeError):
        pass

    # 2. Try SKU lookup
    if not product:
        product = Product.objects.select_related(
            'category', 'sub_category', 'parent'
        ).prefetch_related(
            'media_assets', 'child_variants', 'child_variants__media_assets'
        ).filter(sku__iexact=identifier_str, is_active=True).first()

    # 3. Staff preview fallback (if staff user is logged in, allow viewing inactive)
    if not product and request.user.is_authenticated and request.user.is_staff:
        try:
            val_uuid = uuid.UUID(identifier_str)
            product = Product.objects.select_related(
                'category', 'sub_category', 'parent'
            ).prefetch_related(
                'media_assets', 'child_variants'
            ).filter(id=val_uuid).first()
        except (ValueError, AttributeError):
            product = Product.objects.select_related(
                'category', 'sub_category', 'parent'
            ).prefetch_related(
                'media_assets', 'child_variants'
            ).filter(sku__iexact=identifier_str).first()

    if not product:
        raise Http404(f"Product '{identifier_str}' was not found in the catalog.")

    # 4. Prepare Gallery Images
    gallery_images = []
    if product.image:
        gallery_images.append({
            'id': 'main',
            'url': product.image.url,
            'title': product.name,
            'is_main': True
        })

    image_assets = product.media_assets.filter(asset_type=MediaAsset.AssetType.IMAGE, is_active=True)
    for asset in image_assets:
        asset_url = asset.file.url if asset.file else asset.external_url
        if asset_url:
            # Avoid duplicate if matches main image
            if not product.image or asset_url != product.image.url:
                gallery_images.append({
                    'id': str(asset.id),
                    'url': asset_url,
                    'title': asset.title or product.name,
                    'is_main': False
                })

    # 5. Interactive 3D Model
    three_d_asset = product.media_assets.filter(
        Q(asset_type=MediaAsset.AssetType.THREE_D) |
        Q(file__icontains='.glb') | Q(file__icontains='.gltf') |
        Q(external_url__icontains='.glb') | Q(external_url__icontains='.gltf'),
        is_active=True
    ).first()
    if not three_d_asset and product.parent:
        three_d_asset = product.parent.media_assets.filter(
            Q(asset_type=MediaAsset.AssetType.THREE_D) |
            Q(file__icontains='.glb') | Q(file__icontains='.gltf') |
            Q(external_url__icontains='.glb') | Q(external_url__icontains='.gltf'),
            is_active=True
        ).first()

    three_d_url = None
    if three_d_asset:
        three_d_url = three_d_asset.file.url if three_d_asset.file else three_d_asset.external_url

    # 6. Video
    video_asset = product.media_assets.filter(asset_type=MediaAsset.AssetType.VIDEO, is_active=True).first()
    video_url = None
    if video_asset:
        video_url = video_asset.file.url if video_asset.file else video_asset.external_url

    # 7. PDF Brochures & Technical Sheets
    doc_assets = product.media_assets.filter(
        asset_type__in=[MediaAsset.AssetType.PDF_BROCHURE, MediaAsset.AssetType.TECH_SHEET],
        is_active=True
    )
    documents = []
    for doc in doc_assets:
        doc_url = doc.file.url if doc.file else doc.external_url
        if doc_url:
            documents.append({
                'id': str(doc.id),
                'title': doc.title or ('Technical Specification' if doc.asset_type == MediaAsset.AssetType.TECH_SHEET else 'Product Brochure'),
                'type': 'Technical Sheet' if doc.asset_type == MediaAsset.AssetType.TECH_SHEET else 'Brochure',
                'url': doc_url,
                'file_size_mb': doc.file_size_mb or None,
                'description': doc.description or ''
            })

    # 8. Variants
    parent_product = product.parent if product.parent else product
    family_qs = Product.objects.filter(
        Q(id=parent_product.id) | Q(parent=parent_product),
        is_active=True
    ).order_by('name')

    variants_list = []
    for var in family_qs:
        variants_list.append({
            'id': str(var.id),
            'name': var.name if var.id != parent_product.id else (var.name + " (Base Model)"),
            'display_name': var.name,
            'sku': var.sku,
            'is_current': (var.id == product.id),
            'image_url': var.image.url if var.image else None
        })
    has_variants = len(variants_list) > 1

    # 9. Specifications normalization
    specs_list = []
    if isinstance(product.specifications, dict):
        for k, v in product.specifications.items():
            if v is not None and str(v).strip():
                if isinstance(v, list):
                    val_str = ", ".join(str(item) for item in v)
                elif isinstance(v, dict):
                    val_str = "; ".join(f"{dk}: {dv}" for dk, dv in v.items())
                else:
                    val_str = str(v)
                specs_list.append({'key': k, 'value': val_str})

    # 10. Features normalization
    features_list = []
    if isinstance(product.features, list):
        for f in product.features:
            if isinstance(f, dict):
                title = f.get('title') or f.get('name') or ''
                desc = f.get('description') or f.get('desc') or ''
                sub_points = f.get('sub_points') or f.get('points') or []
                if title or desc:
                    features_list.append({'title': title, 'description': desc, 'sub_points': sub_points})
            elif isinstance(f, str) and f.strip():
                features_list.append({'title': f.strip(), 'description': '', 'sub_points': []})

    # 11. Certifications normalization
    certs_list = []
    if isinstance(product.certifications, list):
        for c in product.certifications:
            if isinstance(c, dict):
                title = c.get('title') or c.get('name') or ''
                desc = c.get('description') or c.get('desc') or ''
                tests = c.get('tests') or []
                if title or desc:
                    certs_list.append({'title': title, 'description': desc, 'tests': tests})
            elif isinstance(c, str) and c.strip():
                certs_list.append({'title': c.strip(), 'description': '', 'tests': []})

    # 12. In-House Tests normalization
    tests_list = []
    if isinstance(product.in_house_tests, list):
        for t in product.in_house_tests:
            if isinstance(t, dict):
                title = t.get('title') or t.get('name') or ''
                desc = t.get('description') or t.get('desc') or ''
                sub_tests = t.get('tests') or []
                if title or desc:
                    tests_list.append({'title': title, 'description': desc, 'tests': sub_tests})
            elif isinstance(t, str) and t.strip():
                tests_list.append({'title': t.strip(), 'description': '', 'tests': []})

    # 13. Applicable Areas
    areas_list = []
    if isinstance(product.applicable_areas, list):
        for a in product.applicable_areas:
            if isinstance(a, str) and a.strip():
                areas_list.append(a.strip())
            elif isinstance(a, dict) and (a.get('name') or a.get('title')):
                areas_list.append(a.get('name') or a.get('title'))

    # Determine default active content tab
    default_tab = ''
    if specs_list:
        default_tab = 'specs'
    elif product.description:
        default_tab = 'overview'
    elif features_list:
        default_tab = 'features'
    elif areas_list:
        default_tab = 'applications'
    elif certs_list or tests_list:
        default_tab = 'testing'
    elif documents:
        default_tab = 'documents'

    context = {
        'product': product,
        'gallery_images': gallery_images,
        'three_d_url': three_d_url,
        'video_url': video_url,
        'documents': documents,
        'has_variants': has_variants,
        'variants_list': variants_list,
        'specs_list': specs_list,
        'features_list': features_list,
        'certs_list': certs_list,
        'tests_list': tests_list,
        'areas_list': areas_list,
        'default_tab': default_tab,
    }
    return render(request, 'public/product_detail.html', context)


def public_product_list(request):
    """
    Public catalogue directory to browse products with live search and category filtering.
    """
    qs = Product.objects.filter(is_active=True, parent__isnull=True).select_related(
        'category', 'sub_category'
    ).prefetch_related('media_assets').order_by('-created_at')

    query = request.GET.get('q', '').strip()
    if query:
        qs = qs.filter(
            Q(name__icontains=query) |
            Q(sku__icontains=query) |
            Q(description__icontains=query) |
            Q(category__name__icontains=query) |
            Q(sub_category__name__icontains=query)
        )

    category_slug = request.GET.get('category', '').strip()
    selected_category = None
    if category_slug and category_slug.lower() != 'all':
        try:
            cat_uuid = uuid.UUID(category_slug)
            selected_category = Category.objects.filter(id=cat_uuid).first()
            if selected_category:
                qs = qs.filter(Q(category=selected_category) | Q(sub_category__category=selected_category))
        except (ValueError, TypeError):
            selected_category = Category.objects.filter(code__iexact=category_slug).first()
            if selected_category:
                qs = qs.filter(Q(category=selected_category) | Q(sub_category__category=selected_category))

    sub_category_slug = request.GET.get('subcategory', '').strip()
    selected_subcategory = None
    if sub_category_slug and sub_category_slug.lower() != 'all':
        try:
            sub_uuid = uuid.UUID(sub_category_slug)
            selected_subcategory = SubCategory.objects.filter(id=sub_uuid).first()
            if selected_subcategory:
                qs = qs.filter(sub_category=selected_subcategory)
        except (ValueError, TypeError):
            selected_subcategory = SubCategory.objects.filter(code__iexact=sub_category_slug).first()
            if selected_subcategory:
                qs = qs.filter(sub_category=selected_subcategory)

    categories = Category.objects.filter(is_active=True).prefetch_related('subcategories').order_by('display_order', 'name')

    paginator = Paginator(qs, 12)
    page = request.GET.get('page', 1)
    try:
        products_page = paginator.page(page)
    except (PageNotAnInteger, EmptyPage):
        products_page = paginator.page(1)

    context = {
        'products': products_page,
        'paginator': paginator,
        'page_obj': products_page,
        'is_paginated': products_page.has_other_pages(),
        'query': query,
        'selected_category': selected_category,
        'selected_subcategory': selected_subcategory,
        'categories': categories,
        'total_count': paginator.count,
        'active_page': 'catalog',
    }
    return render(request, 'public/product_list.html', context)
