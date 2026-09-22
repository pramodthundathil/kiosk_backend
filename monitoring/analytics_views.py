import uuid
from rest_framework import status, views
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.utils import timezone
from django.db.models import Q
from django.utils.dateparse import parse_datetime

from kiosks.authentication import KioskJWTAuthentication
from kiosks.models import KioskDevice
from products.models import Product
from .models import ProductInteraction, KioskUsageSession


class KioskAnalyticsIngestionView(views.APIView):
    """
    POST /api/kiosk/analytics/events/
    Ingests batch of interaction telemetry events and session updates from Kiosk mobile devices.
    Supports JWT-authenticated kiosk sessions as well as hardware MAC address verification.
    """
    authentication_classes = [KioskJWTAuthentication]
    permission_classes = [AllowAny]

    def post(self, request):
        kiosk = getattr(request, 'kiosk', None)
        data = request.data or {}

        # Resolve kiosk by hardware MAC or device_id if unauthenticated
        if not kiosk:
            mac = (
                data.get('mac_address') or 
                data.get('device_id') or 
                request.headers.get('X-Device-MAC') or 
                request.headers.get('X-Device-Id')
            )
            if mac:
                clean_mac = str(mac).strip()
                kiosk = KioskDevice.objects.filter(
                    Q(device_id__iexact=clean_mac) | Q(name__iexact=clean_mac)
                ).first()

        if not kiosk:
            return Response(
                {"error": "Kiosk terminal not recognized. Provide a registered MAC or Authorization Bearer token."},
                status=status.HTTP_404_NOT_FOUND
            )

        if not kiosk.is_active:
            return Response({"error": "This kiosk device is marked inactive."}, status=status.HTTP_403_FORBIDDEN)

        now = timezone.now()
        events_data = data.get('events', [])
        session_data = data.get('session_update')

        # 1. Process Batch Interaction Events
        created_interactions = []
        if isinstance(events_data, list) and events_data:
            # Prefetch products by ID/SKU to minimize queries
            product_ids = set()
            for ev in events_data:
                pid = ev.get('product_id')
                if pid:
                    product_ids.add(str(pid).strip())

            product_map = {}
            if product_ids:
                # Support both UUID and SKU lookups
                uuid_ids = []
                sku_ids = []
                for pid in product_ids:
                    try:
                        uuid.UUID(pid)
                        uuid_ids.append(pid)
                    except (ValueError, AttributeError):
                        sku_ids.append(pid)

                prods = Product.objects.filter(
                    Q(id__in=uuid_ids) | Q(sku__in=sku_ids)
                )
                for p in prods:
                    product_map[str(p.id)] = p
                    product_map[p.sku] = p

            for ev in events_data:
                ev_type = ev.get('event_type', ProductInteraction.InteractionType.CLICK)
                # Validate choices
                valid_types = [c[0] for c in ProductInteraction.InteractionType.choices]
                if ev_type not in valid_types:
                    ev_type = ProductInteraction.InteractionType.CLICK

                pid = str(ev.get('product_id')).strip() if ev.get('product_id') else None
                matched_product = product_map.get(pid) if pid else None

                session_id = ev.get('session_id') or ''
                duration = ev.get('duration_seconds') or 0
                metadata = ev.get('metadata') or {}
                
                # Optional client event timestamp
                client_ts = ev.get('timestamp')
                parsed_ts = parse_datetime(client_ts) if client_ts else None

                interaction = ProductInteraction(
                    kiosk=kiosk,
                    product=matched_product,
                    interaction_type=ev_type,
                    session_id=session_id,
                    duration_seconds=int(duration) if str(duration).isdigit() else 0,
                    metadata=metadata
                )
                if parsed_ts and timezone.is_aware(parsed_ts):
                    interaction.created_at = parsed_ts
                created_interactions.append(interaction)

            if created_interactions:
                ProductInteraction.objects.bulk_create(created_interactions)

        # 2. Process Session Update
        session_updated = False
        if isinstance(session_data, dict) and session_data.get('session_id'):
            sess_id = str(session_data.get('session_id')).strip()
            started_at_str = session_data.get('started_at')
            ended_at_str = session_data.get('ended_at')

            started_at = parse_datetime(started_at_str) if started_at_str else now
            if not started_at:
                started_at = now
            if timezone.is_naive(started_at):
                started_at = timezone.make_aware(started_at)

            ended_at = parse_datetime(ended_at_str) if ended_at_str else None
            if ended_at and timezone.is_naive(ended_at):
                ended_at = timezone.make_aware(ended_at)

            duration = session_data.get('duration_seconds') or 0
            total_clicks = session_data.get('total_clicks') or len(created_interactions)
            products_viewed = session_data.get('products_viewed_count') or 0
            metadata = session_data.get('metadata') or {}

            KioskUsageSession.objects.update_or_create(
                session_id=sess_id,
                defaults={
                    'kiosk': kiosk,
                    'started_at': started_at,
                    'ended_at': ended_at,
                    'duration_seconds': int(duration) if str(duration).isdigit() else 0,
                    'total_clicks': int(total_clicks) if str(total_clicks).isdigit() else 0,
                    'products_viewed_count': int(products_viewed) if str(products_viewed).isdigit() else 0,
                    'metadata': metadata,
                }
            )
            session_updated = True

        return Response({
            "success": True,
            "processed_events": len(created_interactions),
            "session_updated": session_updated,
            "server_time": now.isoformat()
        }, status=status.HTTP_200_OK)
