import math
import uuid
from django.db.models import Q, Count
from rest_framework import views, status, permissions
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

from kiosks.authentication import KioskJWTAuthentication
from kiosks.models import KioskDevice
from products.models import Product, Category
from .models import MediaAsset
from .serializers import MediaLibraryAssetSerializer


class MediaLibraryListAPIView(views.APIView):
    """
    GET /api/media-library/
    GET /api/kiosk/media-library/

    Paginated media library endpoint returning images, brochures, 3D assets, tech sheets, and videos.
    Supports infinite scroll pagination, media type categorization, category filtering, search, and kiosk-specific asset scoping.
    """
    authentication_classes = [KioskJWTAuthentication, JWTAuthentication]
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        base_qs = MediaAsset.objects.select_related(
            'product',
            'product__category',
            'product__sub_category',
            'product__sub_category__category'
        ).filter(is_active=True)

        # 1. Kiosk Scoping: If request is authenticated as a kiosk or passes kiosk_id / device_id
        kiosk = getattr(request, 'kiosk', None)
        kiosk_id = request.query_params.get('kiosk_id')
        device_id = request.query_params.get('device_id') or request.headers.get('X-Device-MAC') or request.headers.get('X-Device-Id')

        if not kiosk and (kiosk_id or device_id):
            query = Q()
            if kiosk_id:
                try:
                    query |= Q(id=uuid.UUID(str(kiosk_id)))
                except (ValueError, TypeError):
                    pass
            if device_id:
                query |= Q(device_id__iexact=device_id) | Q(serial_number__iexact=device_id)
            kiosk = KioskDevice.objects.filter(query).first()

        if kiosk:
            assigned_product_ids = kiosk.assigned_products.values_list('id', flat=True)
            if assigned_product_ids.exists():
                # Include assets belonging to assigned products OR standalone global media assets
                base_qs = base_qs.filter(
                    Q(product_id__in=assigned_product_ids) | Q(product__isnull=True)
                )

        # Build dynamic category counts based on kiosk-scoped query before type filter
        type_counts = dict(
            base_qs.values('asset_type').annotate(total=Count('id')).values_list('asset_type', 'total')
        )
        total_all_count = sum(type_counts.values())

        categories_summary = [
            {'id': 'ALL', 'name': 'All Media', 'icon': 'layers', 'count': total_all_count},
            {'id': 'IMAGE', 'name': 'Images', 'icon': 'image', 'count': type_counts.get('IMAGE', 0)},
            {'id': 'PDF_BROCHURE', 'name': 'Brochures', 'icon': 'file-text', 'count': type_counts.get('PDF_BROCHURE', 0)},
            {'id': 'THREE_D', 'name': '3D Assets', 'icon': 'box', 'count': type_counts.get('THREE_D', 0)},
            {'id': 'TECH_SHEET', 'name': 'Tech Sheets', 'icon': 'file-check', 'count': type_counts.get('TECH_SHEET', 0)},
            {'id': 'VIDEO', 'name': 'Videos', 'icon': 'video', 'count': type_counts.get('VIDEO', 0)},
        ]

        qs = base_qs

        # 2. Filter by asset_type
        asset_type = request.query_params.get('asset_type') or request.query_params.get('type')
        if asset_type and asset_type.upper() != 'ALL':
            qs = qs.filter(asset_type=asset_type.upper())

        # 3. Filter by product category (by ID or Code)
        category_param = request.query_params.get('category_id') or request.query_params.get('category')
        if category_param and category_param.lower() != 'all':
            try:
                cat_uuid = uuid.UUID(category_param)
                qs = qs.filter(
                    Q(product__category__id=cat_uuid) |
                    Q(product__category__code__iexact=category_param) |
                    Q(product__sub_category__category__id=cat_uuid) |
                    Q(product__sub_category__category__code__iexact=category_param)
                )
            except (ValueError, TypeError):
                qs = qs.filter(
                    Q(product__category__code__iexact=category_param) |
                    Q(product__sub_category__category__code__iexact=category_param)
                )

        # 4. Filter by search query
        search_query = request.query_params.get('search', '').strip()
        if search_query:
            qs = qs.filter(
                Q(title__icontains=search_query) |
                Q(description__icontains=search_query) |
                Q(product__name__icontains=search_query) |
                Q(product__sku__icontains=search_query)
            )

        # 5. Order results
        qs = qs.order_by('-created_at')

        # 6. Pagination
        total_items = qs.count()

        try:
            page = max(1, int(request.query_params.get('page', 1)))
        except (ValueError, TypeError):
            page = 1

        try:
            page_size = int(request.query_params.get('page_size', 12))
            page_size = max(1, min(page_size, 100))
        except (ValueError, TypeError):
            page_size = 12

        total_pages = math.ceil(total_items / page_size) if total_items > 0 else 1
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size

        paginated_items = qs[start_idx:end_idx]

        serializer = MediaLibraryAssetSerializer(paginated_items, many=True, context={'request': request})

        return Response({
            'count': total_items,
            'page': page,
            'page_size': page_size,
            'total_pages': total_pages,
            'has_next': page < total_pages,
            'has_previous': page > 1,
            'categories': categories_summary,
            'results': serializer.data,
        }, status=status.HTTP_200_OK)
