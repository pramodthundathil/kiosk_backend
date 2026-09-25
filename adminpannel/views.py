import json
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth import get_user_model

from django.contrib import messages
from django.utils import timezone
from stores.models import Store
from kiosks.models import KioskDevice, KioskProfile, AppRelease, KioskUpdateLog
from kiosks.apk_validator import validate_apk_file, compute_file_sha256_and_size
from kiosks.services import register_kiosk_device, update_kiosk_credential
from monitoring.models import Alert, KioskEvent, ProductInteraction, KioskUsageSession

from monitoring.services import update_kiosk_status_and_alerts
from django.db.models import Q, Count, Sum, Avg, Max, Min, F
from django.db.models.functions import ExtractHour, TruncDate
from datetime import timedelta
import csv
from django.http import HttpResponse
from products.models import Product, Category, SubCategory
from content.models import MediaAsset, Screensaver


User = get_user_model()



def admin_dashboard(request):
    """Overview dashboard view with system-wide stats and alerts."""
    if not request.user.is_authenticated:
        return redirect('signin')

    kiosks = KioskDevice.objects.select_related('store', 'profile').all().order_by('-created_at')
    total_kiosks = kiosks.count()
    online_count = 0
    warning_count = 0
    offline_count = 0
    disabled_count = 0
    kiosk_list = []

    for k in kiosks:
        status = update_kiosk_status_and_alerts(k)
        is_online = (status == KioskDevice.Status.ONLINE)
        if status == KioskDevice.Status.ONLINE:
            online_count += 1
        elif status == KioskDevice.Status.WARNING:
            warning_count += 1
        elif status == KioskDevice.Status.DISABLED:
            disabled_count += 1
        else:
            offline_count += 1

        kiosk_list.append({
            'id': str(k.id),
            'username': k.name,
            'device_id': k.device_id,
            'location': k.store.name if k.store else 'Unspecified Location',
            'status': status,
            'is_online': is_online,
            'last_sync': k.last_sync_at.strftime('%Y-%m-%d %H:%M:%S') if k.last_sync_at else 'Never Synced',
            'last_heartbeat': k.last_heartbeat_at.strftime('%Y-%m-%d %H:%M:%S') if k.last_heartbeat_at else 'Never',
            'app_version': k.app_version or 'v1.0.0',
            'device_info': f"{k.manufacturer or ''} {k.device_model or ''}".strip() or 'Android Kiosk Display',
            'last_boot': k.last_seen_at.strftime('%Y-%m-%d %H:%M:%S') if k.last_seen_at else 'N/A',
            'profile_name': k.profile.name if k.profile else 'Standard'
        })

    open_alerts = Alert.objects.filter(resolved_at__isnull=True).select_related('kiosk', 'kiosk__store')[:15]
    total_products = Product.objects.filter(is_active=True).count()
    total_stores = Store.objects.filter(is_active=True).count()
    total_users = User.objects.count()

    context = {
        'kiosks': kiosk_list,
        'total_kiosks': total_kiosks,
        'online_count': online_count,
        'warning_count': warning_count,
        'offline_count': offline_count,
        'disabled_count': disabled_count,
        'total_products': total_products,
        'total_stores': total_stores,
        'total_users': total_users,
        'open_alerts': open_alerts,
        'active_tab': 'dashboard',
    }
    return render(request, "admin/dashboard.html", context)


def admin_kiosks(request):
    """Dedicated Kiosks Management Page: Add, View, Update, Delete, Sync & Reboot."""
    if not request.user.is_authenticated:
        return redirect('signin')

    if request.method == "POST":
        action = request.POST.get('action')

        if action == "register_kiosk":
            location = request.POST.get('location', '').strip()
            device_id = request.POST.get('device_id', '').strip()
            name = request.POST.get('name', '').strip()
            store_id = request.POST.get('store_id', '').strip()
            profile_id = request.POST.get('profile_id', '').strip()
            latitude_str = request.POST.get('latitude', '').strip()
            longitude_str = request.POST.get('longitude', '').strip()
            is_deployed = request.POST.get('is_deployed') in ['true', 'on', '1']
            custom_secret = request.POST.get('custom_secret', '').strip()

            if not device_id:
                messages.error(request, "Device ID is required to register a kiosk.")
            elif KioskDevice.objects.filter(device_id=device_id).exists():
                messages.error(request, f"Device ID '{device_id}' is already registered.")
            else:
                try:
                    store = Store.objects.filter(id=store_id).first() if store_id else None
                    if not store and location:
                        code = f"STORE-{location[:3].upper()}"
                        store, _ = Store.objects.get_or_create(name=location, defaults={'code': code})

                    profile = KioskProfile.objects.filter(id=profile_id).first() if profile_id else None
                    if not profile:
                        profile, _ = KioskProfile.objects.get_or_create(
                            code="STANDARD",
                            defaults={'name': 'Standard Kiosk Profile', 'description': 'Default layout'}
                        )

                    latitude = float(latitude_str) if latitude_str else None
                    longitude = float(longitude_str) if longitude_str else None

                    kiosk, raw_secret = register_kiosk_device(
                        name=name if name else f"Kiosk-{device_id}",
                        device_id=device_id,
                        store=store,
                        profile=profile,
                        custom_secret=custom_secret,
                        latitude=latitude,
                        longitude=longitude,
                        is_deployed=is_deployed
                    )
                    messages.success(
                        request,
                        f"Kiosk [{kiosk.device_id}] registered successfully! DEVICE SECRET: '{raw_secret}'"
                    )
                except Exception as e:
                    messages.error(request, f"Error registering kiosk: {str(e)}")
            return redirect('admin_kiosks')

        elif action == "update_kiosk":
            kiosk_id = request.POST.get('kiosk_id')
            name = request.POST.get('name', '').strip()
            store_id = request.POST.get('store_id', '').strip()
            profile_id = request.POST.get('profile_id', '').strip()
            desired_ver = request.POST.get('desired_content_version', '1').strip()
            latitude_str = request.POST.get('latitude', '').strip()
            longitude_str = request.POST.get('longitude', '').strip()
            is_deployed = request.POST.get('is_deployed') in ['true', 'on', '1']

            try:
                kiosk = KioskDevice.objects.get(id=kiosk_id)
                if name:
                    kiosk.name = name
                kiosk.store = Store.objects.filter(id=store_id).first() if store_id else None
                kiosk.profile = KioskProfile.objects.filter(id=profile_id).first() if profile_id else None
                kiosk.desired_content_version = desired_ver
                
                kiosk.latitude = float(latitude_str) if latitude_str else None
                kiosk.longitude = float(longitude_str) if longitude_str else None
                
                if is_deployed and not kiosk.is_deployed:
                    kiosk.deployed_at = timezone.now()
                elif not is_deployed:
                    kiosk.deployed_at = None
                kiosk.is_deployed = is_deployed

                kiosk.save()
                messages.success(request, f"Kiosk '{kiosk.name}' updated successfully.")
            except KioskDevice.DoesNotExist:
                messages.error(request, "Kiosk device not found.")
            return redirect('admin_kiosks')

        elif action == "delete_kiosk":
            kiosk_id = request.POST.get('kiosk_id')
            try:
                kiosk = KioskDevice.objects.get(id=kiosk_id)
                kiosk.delete()
                messages.success(request, "Kiosk device deleted successfully.")
            except KioskDevice.DoesNotExist:
                messages.error(request, "Kiosk device not found.")
            return redirect('admin_kiosks')

        elif action == "force_sync":
            kiosk_id = request.POST.get('kiosk_id')
            redirect_to = request.POST.get('next') or request.META.get('HTTP_REFERER')
            try:
                kiosk = KioskDevice.objects.get(id=kiosk_id)
                current_ver = int(kiosk.desired_content_version) if (kiosk.desired_content_version and kiosk.desired_content_version.isdigit()) else 1
                kiosk.desired_content_version = str(current_ver + 1)
                kiosk.save(update_fields=['desired_content_version'])
                KioskEvent.objects.create(
                    kiosk=kiosk,
                    event_type=KioskEvent.EventType.SYNC_STARTED,
                    severity=KioskEvent.Severity.INFO,
                    message=f"Force sync triggered by admin ({request.user.username}). Desired version set to v{kiosk.desired_content_version}."
                )
                messages.success(request, f"Force Sync requested for Kiosk [{kiosk.device_id}]. Target content version set to v{kiosk.desired_content_version}.")
            except KioskDevice.DoesNotExist:
                messages.error(request, "Kiosk device not found.")
            if redirect_to and ('/admin_pannel/' in redirect_to):
                return redirect(redirect_to)
            return redirect('admin_kiosks')

    kiosks = KioskDevice.objects.select_related('store', 'profile').prefetch_related('assigned_products').all().order_by('-created_at')
    stores = Store.objects.filter(is_active=True).order_by('name')
    profiles = KioskProfile.objects.filter(is_active=True).order_by('name')

    kiosk_list = []
    for k in kiosks:
        status = update_kiosk_status_and_alerts(k)
        kiosk_list.append({
            'id': str(k.id),
            'name': k.name,
            'device_id': k.device_id,
            'store_name': k.store.name if k.store else 'Unassigned Store',
            'store_id': str(k.store.id) if k.store else '',
            'profile_name': k.profile.name if k.profile else 'Standard',
            'profile_id': str(k.profile.id) if k.profile else '',
            'status': status,
            'is_online': (status == KioskDevice.Status.ONLINE),
            'is_deployed': k.is_deployed,
            'deployed_at': k.deployed_at.strftime('%Y-%m-%d %H:%M') if k.deployed_at else 'Not Deployed',
            'latitude': str(k.latitude) if k.latitude is not None else '',
            'longitude': str(k.longitude) if k.longitude is not None else '',
            'last_sync': k.last_sync_at.strftime('%Y-%m-%d %H:%M:%S') if k.last_sync_at else 'Never Synced',
            'app_version': k.app_version or 'v1.0.0',
            'current_content_version': k.current_content_version,
            'desired_content_version': k.desired_content_version,
            'device_info': f"{k.manufacturer or ''} {k.device_model or ''}".strip() or 'Android Kiosk Display',
            'last_boot': k.last_seen_at.strftime('%Y-%m-%d %H:%M:%S') if k.last_seen_at else 'N/A',
            'assigned_products_count': k.assigned_products.count(),
        })

    context = {
        'kiosks': kiosk_list,
        'stores': stores,
        'profiles': profiles,
        'active_tab': 'kiosks',
        'page_title': 'Physical Kiosk Terminals Directory',
        'breadcrumbs': [
            {'name': 'Kiosks Directory', 'url': ''}
        ]
    }
    return render(request, "admin/kiosks.html", context)


def admin_kiosk_add(request):
    """Dedicated Page to Register a New Kiosk Terminal with Credentials & Hardware Specs."""
    if not request.user.is_authenticated:
        return redirect('signin')

    if request.method == "POST":
        device_id = request.POST.get('device_id', '').strip()
        name = request.POST.get('name', '').strip()
        store_id = request.POST.get('store_id', '').strip()
        location = request.POST.get('location', '').strip()
        profile_id = request.POST.get('profile_id', '').strip()
        new_profile_name = request.POST.get('new_profile_name', '').strip()
        new_profile_code = request.POST.get('new_profile_code', '').strip()
        latitude_str = request.POST.get('latitude', '').strip()
        longitude_str = request.POST.get('longitude', '').strip()
        is_deployed = request.POST.get('is_deployed') in ['true', 'on', '1']
        custom_secret = request.POST.get('custom_secret', '').strip()

        # Hardware specifications
        manufacturer = request.POST.get('manufacturer', '').strip()
        device_model = request.POST.get('device_model', '').strip()
        serial_number = request.POST.get('serial_number', '').strip()
        android_version = request.POST.get('android_version', '').strip()
        app_version = request.POST.get('app_version', '').strip()
        width_str = request.POST.get('screen_width', '').strip()
        height_str = request.POST.get('screen_height', '').strip()

        if not device_id:
            messages.error(request, "Device ID is required to register a kiosk.")
            return redirect('admin_kiosk_add')
        elif KioskDevice.objects.filter(device_id=device_id).exists():
            messages.error(request, f"Device ID '{device_id}' is already registered.")
            return redirect('admin_kiosk_add')

        try:
            store = Store.objects.filter(id=store_id).first() if store_id else None
            if not store and location:
                code = f"STORE-{location[:3].upper()}"
                store, _ = Store.objects.get_or_create(name=location, defaults={'code': code})

            profile_option_type = request.POST.get('profile_option_type', 'select')
            profile = None

            if profile_option_type == 'select' and profile_id:
                profile = KioskProfile.objects.filter(id=profile_id).first()

            if not profile:
                show_products = request.POST.get('show_products') in ['true', 'on', '1']
                show_brochures = request.POST.get('show_brochures') in ['true', 'on', '1']
                show_technical_documents = request.POST.get('show_technical_documents') in ['true', 'on', '1']
                show_pricing = request.POST.get('show_pricing') in ['true', 'on', '1']
                show_videos = request.POST.get('show_videos') in ['true', 'on', '1']
                show_3d_assets = request.POST.get('show_3d_assets') in ['true', 'on', '1']
                show_whiteboard = request.POST.get('show_whiteboard') in ['true', 'on', '1']
                screensaver_enabled = request.POST.get('screensaver_enabled') in ['true', 'on', '1']
                timeout_str = request.POST.get('screensaver_timeout_seconds', '300').strip()
                screensaver_timeout_seconds = int(timeout_str) if timeout_str.isdigit() else 300

                prof_code = (new_profile_code.upper() if new_profile_code else f"PROF-{device_id[:8].upper()}")
                prof_name = new_profile_name if new_profile_name else f"Profile ({name or device_id})"

                profile = KioskProfile.objects.create(
                    name=prof_name,
                    code=prof_code,
                    show_products=show_products,
                    show_brochures=show_brochures,
                    show_technical_documents=show_technical_documents,
                    show_pricing=show_pricing,
                    show_videos=show_videos,
                    show_3d_assets=show_3d_assets,
                    show_whiteboard=show_whiteboard,
                    screensaver_enabled=screensaver_enabled,
                    screensaver_timeout_seconds=screensaver_timeout_seconds
                )

            latitude = float(latitude_str) if latitude_str else None
            longitude = float(longitude_str) if longitude_str else None
            screen_width = int(width_str) if width_str.isdigit() else None
            screen_height = int(height_str) if height_str.isdigit() else None

            kiosk, raw_secret = register_kiosk_device(
                name=name if name else f"Kiosk-{device_id}",
                device_id=device_id,
                store=store,
                profile=profile,
                custom_secret=custom_secret,
                latitude=latitude,
                longitude=longitude,
                is_deployed=is_deployed,
                manufacturer=manufacturer,
                device_model=device_model,
                serial_number=serial_number,
                android_version=android_version,
                app_version=app_version,
                screen_width=screen_width,
                screen_height=screen_height
            )
            messages.success(
                request,
                f"Kiosk [{kiosk.device_id}] registered successfully with profile '{profile.name}'! DEVICE SECRET: '{raw_secret}'"
            )
            return redirect('admin_kiosks')
        except Exception as e:
            messages.error(request, f"Error registering kiosk: {str(e)}")
            return redirect('admin_kiosk_add')

    stores = Store.objects.filter(is_active=True).order_by('name')
    profiles = KioskProfile.objects.filter(is_active=True).order_by('name')

    context = {
        'stores': stores,
        'profiles': profiles,
        'active_tab': 'kiosks',
        'page_title': 'Register New Kiosk Terminal',
        'breadcrumbs': [
            {'name': 'Kiosks Directory', 'url': '/admin_pannel/kiosks/'},
            {'name': 'Register New Kiosk', 'url': ''}
        ]
    }
    return render(request, "admin/kiosk_add.html", context)


def admin_kiosk_edit(request, kiosk_id):
    """Dedicated Page to Edit Kiosk Settings, Profile Options, Hardware Specs & Credentials."""
    if not request.user.is_authenticated:
        return redirect('signin')

    kiosk = get_object_or_404(KioskDevice, id=kiosk_id)

    if request.method == "POST":
        action = request.POST.get('action', 'update_kiosk')

        if action == "update_credentials":
            new_secret = request.POST.get('new_secret', '').strip()
            if not new_secret:
                messages.error(request, "Password/Secret cannot be empty.")
            else:
                update_kiosk_credential(kiosk, new_secret)
                messages.success(request, f"Credentials updated for [{kiosk.device_id}]. New Device Secret: '{new_secret}'")
            return redirect('admin_kiosk_edit', kiosk_id=kiosk.id)

        name = request.POST.get('name', '').strip()
        store_id = request.POST.get('store_id', '').strip()
        profile_id = request.POST.get('profile_id', '').strip()
        desired_ver = request.POST.get('desired_content_version', '1').strip()
        latitude_str = request.POST.get('latitude', '').strip()
        longitude_str = request.POST.get('longitude', '').strip()
        is_deployed = request.POST.get('is_deployed') in ['true', 'on', '1']

        # Hardware specifications
        kiosk.manufacturer = request.POST.get('manufacturer', '').strip() or None
        kiosk.device_model = request.POST.get('device_model', '').strip() or None
        kiosk.serial_number = request.POST.get('serial_number', '').strip() or None
        kiosk.android_version = request.POST.get('android_version', '').strip() or None
        kiosk.app_version = request.POST.get('app_version', '').strip() or None
        width_str = request.POST.get('screen_width', '').strip()
        height_str = request.POST.get('screen_height', '').strip()
        kiosk.screen_width = int(width_str) if width_str.isdigit() else None
        kiosk.screen_height = int(height_str) if height_str.isdigit() else None

        if name:
            kiosk.name = name
        kiosk.store = Store.objects.filter(id=store_id).first() if store_id else None
        
        # Profile handling
        if profile_id:
            kiosk.profile = KioskProfile.objects.filter(id=profile_id).first()
        
        # Update profile feature flags if profile exists
        if kiosk.profile and request.POST.get('update_profile_features') == 'true':
            kiosk.profile.show_products = request.POST.get('show_products') in ['true', 'on', '1']
            kiosk.profile.show_brochures = request.POST.get('show_brochures') in ['true', 'on', '1']
            kiosk.profile.show_technical_documents = request.POST.get('show_technical_documents') in ['true', 'on', '1']
            kiosk.profile.show_pricing = request.POST.get('show_pricing') in ['true', 'on', '1']
            kiosk.profile.show_videos = request.POST.get('show_videos') in ['true', 'on', '1']
            kiosk.profile.show_3d_assets = request.POST.get('show_3d_assets') in ['true', 'on', '1']
            kiosk.profile.show_whiteboard = request.POST.get('show_whiteboard') in ['true', 'on', '1']
            kiosk.profile.screensaver_enabled = request.POST.get('screensaver_enabled') in ['true', 'on', '1']
            timeout_str = request.POST.get('screensaver_timeout_seconds', '300').strip()
            kiosk.profile.screensaver_timeout_seconds = int(timeout_str) if timeout_str.isdigit() else 300
            kiosk.profile.save()

        kiosk.desired_content_version = desired_ver
        kiosk.latitude = float(latitude_str) if latitude_str else None
        kiosk.longitude = float(longitude_str) if longitude_str else None

        if is_deployed and not kiosk.is_deployed:
            kiosk.deployed_at = timezone.now()
        elif not is_deployed:
            kiosk.deployed_at = None
        kiosk.is_deployed = is_deployed

        kiosk.save()
        messages.success(request, f"Kiosk '{kiosk.name}' settings and profile options updated successfully.")
        return redirect('admin_kiosks')

    stores = Store.objects.filter(is_active=True).order_by('name')
    profiles = KioskProfile.objects.filter(is_active=True).order_by('name')

    context = {
        'kiosk': kiosk,
        'stores': stores,
        'profiles': profiles,
        'active_tab': 'kiosks',
        'page_title': f'Edit Kiosk: {kiosk.name}',
        'breadcrumbs': [
            {'name': 'Kiosks Directory', 'url': '/admin_pannel/kiosks/'},
            {'name': f'Edit ({kiosk.device_id})', 'url': ''}
        ]
    }
    return render(request, "admin/kiosk_edit.html", context)


def admin_kiosk_detail(request, kiosk_id):
    """Single detailed view of a specific kiosk terminal with hardware specs, store, profile, telemetry, product assignments, and edit links."""
    if not request.user.is_authenticated:
        return redirect('signin')

    kiosk = get_object_or_404(KioskDevice.objects.select_related('store', 'profile'), id=kiosk_id)

    if request.method == "POST":
        action = request.POST.get('action')

        if action == "assign_products":
            product_ids = request.POST.getlist('product_ids')
            kiosk.assigned_products.set(product_ids)
            current_ver = int(kiosk.desired_content_version) if (kiosk.desired_content_version and kiosk.desired_content_version.isdigit()) else 1
            kiosk.desired_content_version = str(current_ver + 1)
            kiosk.save(update_fields=['desired_content_version'])
            KioskEvent.objects.create(
                kiosk=kiosk,
                event_type=KioskEvent.EventType.SYNC_STARTED,
                severity=KioskEvent.Severity.INFO,
                message=f"Assigned products updated by admin ({request.user.username}). Target content version bumped to v{kiosk.desired_content_version}."
            )
            messages.success(request, f"Updated assigned products display for kiosk '{kiosk.name}' ({len(product_ids)} items). Content sync version bumped to v{kiosk.desired_content_version}.")
            return redirect('admin_kiosk_detail', kiosk_id=kiosk.id)

        elif action == "remove_assigned_product":
            product_id = request.POST.get('product_id')
            if product_id:
                kiosk.assigned_products.remove(product_id)
                current_ver = int(kiosk.desired_content_version) if (kiosk.desired_content_version and kiosk.desired_content_version.isdigit()) else 1
                kiosk.desired_content_version = str(current_ver + 1)
                kiosk.save(update_fields=['desired_content_version'])
                KioskEvent.objects.create(
                    kiosk=kiosk,
                    event_type=KioskEvent.EventType.SYNC_STARTED,
                    severity=KioskEvent.Severity.INFO,
                    message=f"Product removed from display by admin ({request.user.username}). Target content version bumped to v{kiosk.desired_content_version}."
                )
                messages.success(request, f"Removed product from kiosk '{kiosk.name}' display. Content sync version bumped to v{kiosk.desired_content_version}.")
            return redirect('admin_kiosk_detail', kiosk_id=kiosk.id)

        elif action == "force_sync":
            current_ver = int(kiosk.desired_content_version) if (kiosk.desired_content_version and kiosk.desired_content_version.isdigit()) else 1
            kiosk.desired_content_version = str(current_ver + 1)
            kiosk.save(update_fields=['desired_content_version'])
            KioskEvent.objects.create(
                kiosk=kiosk,
                event_type=KioskEvent.EventType.SYNC_STARTED,
                severity=KioskEvent.Severity.INFO,
                message=f"Force sync triggered by admin ({request.user.username}). Target version set to v{kiosk.desired_content_version}."
            )
            messages.success(request, f"Force Sync requested for Kiosk '{kiosk.name}' [{kiosk.device_id}]. Target content version set to v{kiosk.desired_content_version}. The kiosk terminal will collect latest data (screensavers, products, categories) on its next heartbeat.")
            return redirect('admin_kiosk_detail', kiosk_id=kiosk.id)

        elif action == "check_update":
            kiosk.check_update_requested = True
            kiosk.save(update_fields=['check_update_requested'])
            KioskEvent.objects.create(
                kiosk=kiosk,
                event_type=KioskEvent.EventType.APP_UPDATE,
                severity=KioskEvent.Severity.INFO,
                message=f"Remote check-update dispatched by admin ({request.user.username})."
            )
            messages.success(request, f"Check Update signal queued for Kiosk '{kiosk.name}' [{kiosk.device_id}]. The device will check for new releases on its next ping.")
            return redirect('admin_kiosk_detail', kiosk_id=kiosk.id)

        elif action == "force_update":
            kiosk.force_update_requested = True
            kiosk.save(update_fields=['force_update_requested'])
            KioskEvent.objects.create(
                kiosk=kiosk,
                event_type=KioskEvent.EventType.APP_UPDATE,
                severity=KioskEvent.Severity.WARNING,
                message=f"Remote force-update dispatched by admin ({request.user.username})."
            )
            messages.success(request, f"Force Update signal queued for Kiosk '{kiosk.name}' [{kiosk.device_id}]. The device will download and install the latest published release on its next ping.")
            return redirect('admin_kiosk_detail', kiosk_id=kiosk.id)

    status = update_kiosk_status_and_alerts(kiosk)
    recent_events = KioskEvent.objects.filter(kiosk=kiosk).order_by('-created_at')[:15]
    open_alerts = Alert.objects.filter(kiosk=kiosk, resolved_at__isnull=True).order_by('-opened_at')

    assigned_products = kiosk.assigned_products.select_related('category').prefetch_related('media_assets').filter(is_active=True).order_by('-created_at')
    assigned_product_ids = set(kiosk.assigned_products.values_list('id', flat=True))
    all_products = Product.objects.select_related('category').filter(is_active=True).order_by('name')
    categories = Category.objects.filter(is_active=True).order_by('name')
    latest_release = AppRelease.objects.filter(is_published=True, is_active=True).order_by('-version_code').first()

    context = {
        'kiosk': kiosk,
        'status': status,
        'is_online': (status == KioskDevice.Status.ONLINE),
        'recent_events': recent_events,
        'open_alerts': open_alerts,
        'assigned_products': assigned_products,
        'assigned_product_ids': assigned_product_ids,
        'all_products': all_products,
        'categories': categories,
        'latest_release': latest_release,
        'active_tab': 'kiosks',
        'page_title': f'Kiosk Terminal Details: {kiosk.name}',
        'breadcrumbs': [
            {'name': 'Kiosks Directory', 'url': '/admin_pannel/kiosks/'},
            {'name': f'Terminal Details ({kiosk.device_id})', 'url': ''}
        ]
    }

    return render(request, "admin/kiosk_detail.html", context)


def admin_products(request):
    """Dedicated Products Management Page: Add, List, Update, Delete Products & Categories."""
    if not request.user.is_authenticated:
        return redirect('signin')

    if request.method == "POST":
        action = request.POST.get('action')

        if action == "add_product":
            name = request.POST.get('name', '').strip()
            sku = request.POST.get('sku', '').strip()
            category_id = request.POST.get('category_id', '').strip()
            price = request.POST.get('price', '0.00').strip()
            stock = request.POST.get('stock', '100').strip()
            description = request.POST.get('description', '').strip()
            image = request.FILES.get('image')

            if not name or not sku:
                messages.error(request, "Product Name and SKU code are required.")
                return redirect('admin_products')
            elif Product.objects.filter(sku=sku).exists():
                messages.error(request, f"Product SKU '{sku}' already exists.")
                return redirect('admin_products')
            else:
                category = Category.objects.filter(id=category_id).first() if category_id else None
                product = Product.objects.create(
                    name=name,
                    sku=sku,
                    category=category,
                    price=price or 0.00,
                    stock=stock or 100,
                    description=description,
                    image=image
                )
                messages.success(request, f"Product '{name}' added successfully! You can now configure specifications and media assets.")
                return redirect('admin_product_detail', product_id=product.id)

        elif action == "update_product":
            product_id = request.POST.get('product_id')
            try:
                product = Product.objects.get(id=product_id)
                product.name = request.POST.get('name', product.name).strip()
                product.price = request.POST.get('price', product.price)
                product.stock = request.POST.get('stock', product.stock)
                product.description = request.POST.get('description', product.description).strip()
                cat_id = request.POST.get('category_id', '').strip()
                subcat_id = request.POST.get('sub_category_id', '').strip()
                product.sub_category = SubCategory.objects.filter(id=subcat_id).first() if subcat_id else None
                product.category = Category.objects.filter(id=cat_id).first() if cat_id else (product.sub_category.category if product.sub_category else None)
                if request.FILES.get('image'):
                    product.image = request.FILES.get('image')
                product.save()
                messages.success(request, f"Product '{product.name}' updated successfully.")
            except Product.DoesNotExist:
                messages.error(request, "Product not found.")
            return redirect('admin_products')

        elif action == "delete_product":
            product_id = request.POST.get('product_id')
            try:
                product = Product.objects.get(id=product_id)
                product.delete()
                messages.success(request, "Product removed from catalog.")
            except Product.DoesNotExist:
                messages.error(request, "Product not found.")
            return redirect('admin_products')

        elif action == "add_category":
            cat_name = request.POST.get('name', '').strip()
            cat_code = request.POST.get('code', '').strip()
            if cat_name and cat_code:
                Category.objects.get_or_create(code=cat_code.upper(), defaults={'name': cat_name})
                messages.success(request, f"Category '{cat_name}' created.")
            return redirect('admin_products')

        elif action == "add_subcategory":
            cat_id = request.POST.get('category_id')
            sub_name = request.POST.get('name', '').strip()
            sub_code = request.POST.get('code', '').strip()
            if cat_id and sub_name and sub_code:
                category = Category.objects.filter(id=cat_id).first()
                if category:
                    SubCategory.objects.get_or_create(
                        category=category,
                        code=sub_code.upper(),
                        defaults={'name': sub_name}
                    )
                    messages.success(request, f"Sub-Category '{sub_name}' created under '{category.name}'.")
            return redirect('admin_products')

    selected_cat_id = request.GET.get('category', '').strip()
    selected_subcat_id = request.GET.get('subcategory', '').strip()

    products = Product.objects.select_related('category', 'sub_category').prefetch_related('media_assets', 'assigned_kiosks').filter(is_active=True).order_by('-created_at')

    if selected_cat_id and selected_cat_id != 'all':
        products = products.filter(category_id=selected_cat_id)
    if selected_subcat_id and selected_subcat_id != 'all':
        products = products.filter(sub_category_id=selected_subcat_id)

    categories = Category.objects.filter(is_active=True).prefetch_related('subcategories').order_by('display_order', 'name')
    subcategories = SubCategory.objects.filter(is_active=True).select_related('category').order_by('category__name', 'display_order', 'name')

    context = {
        'products': products,
        'categories': categories,
        'subcategories': subcategories,
        'selected_cat_id': selected_cat_id,
        'selected_subcat_id': selected_subcat_id,
        'total_products': products.count(),
        'active_tab': 'products',
        'page_title': 'Product Catalog Management',
        'breadcrumbs': [
            {'name': 'Products Directory', 'url': ''}
        ]
    }
    return render(request, "admin/products.html", context)


def admin_product_add(request):
    """Dedicated Page to Add a New Product and immediately redirect to its Details & Media Workspace."""
    if not request.user.is_authenticated:
        return redirect('signin')

    if request.method == "POST":
        name = request.POST.get('name', '').strip()
        sku = request.POST.get('sku', '').strip()
        category_id = request.POST.get('category_id', '').strip()
        sub_category_id = request.POST.get('sub_category_id', '').strip()
        price = request.POST.get('price', '0.00').strip()
        stock = request.POST.get('stock', '100').strip()
        description = request.POST.get('description', '').strip()
        image = request.FILES.get('image')

        # Dynamic Specifications processing if submitted
        spec_keys = request.POST.getlist('spec_key')
        spec_values = request.POST.getlist('spec_value')
        specs_dict = {}
        for k, v in zip(spec_keys, spec_values):
            k_clean = k.strip()
            v_clean = v.strip()
            if k_clean:
                specs_dict[k_clean] = v_clean

        if not name or not sku:
            messages.error(request, "Product Name and SKU code are required.")
            return redirect('admin_product_add')
        elif Product.objects.filter(sku=sku).exists():
            messages.error(request, f"Product SKU '{sku}' already exists.")
            return redirect('admin_product_add')

        sub_category = SubCategory.objects.filter(id=sub_category_id).first() if sub_category_id else None
        category = Category.objects.filter(id=category_id).first() if category_id else (sub_category.category if sub_category else None)

        product = Product.objects.create(
            name=name,
            sku=sku,
            category=category,
            sub_category=sub_category,
            price=price or 0.00,
            stock=stock or 100,
            description=description,
            specifications=specs_dict,
            image=image
        )

        # Handle initial media upload if provided during creation
        files = request.FILES.getlist('initial_media_files')
        asset_type = request.POST.get('initial_asset_type', MediaAsset.AssetType.IMAGE)
        if files:
            for f in files:
                file_size = round(f.size / (1024 * 1024), 2)
                MediaAsset.objects.create(
                    title=f"{product.name} - {f.name}",
                    asset_type=asset_type,
                    file=f,
                    file_size_mb=file_size,
                    product=product
                )

        messages.success(request, f"Product '{name}' created successfully! Add specifications and media assets below.")
        return redirect('admin_product_detail', product_id=product.id)

    categories = Category.objects.filter(is_active=True).prefetch_related('subcategories').order_by('display_order', 'name')
    subcategories = SubCategory.objects.filter(is_active=True).select_related('category').order_by('display_order', 'name')

    context = {
        'categories': categories,
        'subcategories': subcategories,
        'active_tab': 'products',
        'page_title': 'Add New Product to Catalog',
        'breadcrumbs': [
            {'name': 'Products Directory', 'url': '/admin_pannel/products/'},
            {'name': 'Add New Product', 'url': ''}
        ]
    }
    return render(request, "admin/product_add.html", context)


def admin_product_detail(request, product_id):
    """Detailed Product Workspace: Edit Info, Dynamic Specifications & Multi-Media Assets (Images, Videos, PDF Brochures, Tech Specs, 3D Assets)."""
    if not request.user.is_authenticated:
        return redirect('signin')

    product = get_object_or_404(Product.objects.select_related('category', 'sub_category').prefetch_related('media_assets'), id=product_id)

    if request.method == "POST":
        action = request.POST.get('action')

        if action == "update_product":
            product.name = request.POST.get('name', product.name).strip()
            product.sku = request.POST.get('sku', product.sku).strip()
            product.price = request.POST.get('price', product.price)
            product.stock = request.POST.get('stock', product.stock)
            product.description = request.POST.get('description', product.description).strip()
            cat_id = request.POST.get('category_id', '').strip()
            subcat_id = request.POST.get('sub_category_id', '').strip()
            product.sub_category = SubCategory.objects.filter(id=subcat_id).first() if subcat_id else None
            product.category = Category.objects.filter(id=cat_id).first() if cat_id else (product.sub_category.category if product.sub_category else None)
            if request.FILES.get('image'):
                product.image = request.FILES.get('image')
            product.save()
            messages.success(request, f"Product '{product.name}' basic information updated successfully.")
            return redirect('admin_product_detail', product_id=product.id)

        elif action == "update_specifications":
            spec_keys = request.POST.getlist('spec_key')
            spec_values = request.POST.getlist('spec_value')
            
            specs_dict = {}
            for k, v in zip(spec_keys, spec_values):
                k_clean = k.strip()
                v_clean = v.strip()
                if k_clean:
                    specs_dict[k_clean] = v_clean
            
            product.specifications = specs_dict
            product.save(update_fields=['specifications', 'updated_at'])
            messages.success(request, f"Product specifications updated successfully ({len(specs_dict)} items).")
            return redirect('admin_product_detail', product_id=product.id)

        elif action == "upload_media":
            title = request.POST.get('title', '').strip()
            asset_type = request.POST.get('asset_type', MediaAsset.AssetType.IMAGE)
            description = request.POST.get('description', '').strip()
            external_url = request.POST.get('external_url', '').strip()
            files = request.FILES.getlist('files')

            if not title and files:
                title = f"{product.name} - {asset_type}"

            if not title and not files and not external_url:
                messages.error(request, "Media asset title and file/link are required.")
            else:
                uploaded_count = 0
                if files:
                    for f in files:
                        file_size = round(f.size / (1024 * 1024), 2)
                        asset_title = title if len(files) == 1 else f"{title or product.name} ({f.name})"
                        MediaAsset.objects.create(
                            title=asset_title,
                            asset_type=asset_type,
                            file=f,
                            external_url=external_url,
                            file_size_mb=file_size,
                            product=product,
                            description=description
                        )
                        uploaded_count += 1
                elif external_url:
                    MediaAsset.objects.create(
                        title=title or f"{product.name} Link",
                        asset_type=asset_type,
                        external_url=external_url,
                        product=product,
                        description=description
                    )
                    uploaded_count += 1
                else:
                    messages.error(request, "Please provide a file to upload or an external URL.")
                    return redirect('admin_product_detail', product_id=product.id)

                messages.success(request, f"Uploaded {uploaded_count} media asset(s) to product '{product.name}'.")
            return redirect('admin_product_detail', product_id=product.id)

        elif action == "delete_media":
            asset_id = request.POST.get('asset_id')
            try:
                asset = MediaAsset.objects.get(id=asset_id, product=product)
                asset.delete()
                messages.success(request, "Media asset removed from product.")
            except MediaAsset.DoesNotExist:
                messages.error(request, "Media asset not found.")
            return redirect('admin_product_detail', product_id=product.id)

        elif action == "assign_kiosks":
            kiosk_ids = request.POST.getlist('kiosk_ids')
            product.assigned_kiosks.set(kiosk_ids)
            messages.success(request, f"Updated kiosk display availability for '{product.name}' ({len(kiosk_ids)} kiosks).")
            return redirect('admin_product_detail', product_id=product.id)

    categories = Category.objects.filter(is_active=True).prefetch_related('subcategories').order_by('display_order', 'name')
    subcategories = SubCategory.objects.filter(is_active=True).select_related('category').order_by('display_order', 'name')
    media_items = product.media_assets.filter(is_active=True).order_by('-created_at')

    # Kiosk Display Assignments
    assigned_kiosks = product.assigned_kiosks.select_related('store', 'profile').filter(is_active=True).order_by('name')
    assigned_kiosk_ids = set(product.assigned_kiosks.values_list('id', flat=True))
    all_kiosks = KioskDevice.objects.select_related('store').filter(is_active=True).order_by('name')

    # Media breakdown counts
    media_counts = {
        'total': media_items.count(),
        'images': media_items.filter(asset_type=MediaAsset.AssetType.IMAGE).count(),
        'videos': media_items.filter(asset_type=MediaAsset.AssetType.VIDEO).count(),
        'brochures': media_items.filter(asset_type=MediaAsset.AssetType.PDF_BROCHURE).count(),
        'tech_sheets': media_items.filter(asset_type=MediaAsset.AssetType.TECH_SHEET).count(),
        'three_d': media_items.filter(asset_type=MediaAsset.AssetType.THREE_D).count(),
    }

    context = {
        'product': product,
        'categories': categories,
        'subcategories': subcategories,
        'media_items': media_items,
        'media_counts': media_counts,
        'asset_types': MediaAsset.AssetType.choices,
        'assigned_kiosks': assigned_kiosks,
        'assigned_kiosk_ids': assigned_kiosk_ids,
        'all_kiosks': all_kiosks,
        'active_tab': 'products',
        'page_title': f'Product Details & Media Workspace: {product.name}',
        'breadcrumbs': [
            {'name': 'Products Directory', 'url': '/admin_pannel/products/'},
            {'name': f'Product Details ({product.sku})', 'url': ''}
        ]
    }
    return render(request, "admin/product_detail.html", context)


def admin_categories(request):
    """Dedicated Categories & Sub-Categories Management Page: Add, Edit, Delete Categories and Sub-Categories."""
    if not request.user.is_authenticated:
        return redirect('signin')

    if request.method == "POST":
        action = request.POST.get('action')

        # ── Main Category Actions ──
        if action == "add_category":
            cat_name = request.POST.get('name', '').strip()
            cat_code = request.POST.get('code', '').strip()
            description = request.POST.get('description', '').strip()
            image = request.FILES.get('image')
            display_order = int(request.POST.get('display_order', 0) or 0)

            if not cat_name or not cat_code:
                messages.error(request, "Category Name and Code are required.")
            elif Category.objects.filter(code=cat_code.upper()).exists():
                messages.error(request, f"Category code '{cat_code.upper()}' already exists.")
            else:
                cat = Category.objects.create(
                    name=cat_name,
                    code=cat_code.upper(),
                    description=description,
                    display_order=display_order,
                )
                if image:
                    cat.image = image
                    cat.save()
                messages.success(request, f"Category '{cat_name}' created successfully.")
            return redirect('admin_categories')

        elif action == "update_category":
            category_id = request.POST.get('category_id')
            try:
                cat = Category.objects.get(id=category_id)
                cat.name = request.POST.get('name', cat.name).strip()
                cat.description = request.POST.get('description', cat.description or '').strip()
                cat.display_order = int(request.POST.get('display_order', cat.display_order) or 0)
                if request.FILES.get('image'):
                    cat.image = request.FILES.get('image')
                cat.save()
                messages.success(request, f"Category '{cat.name}' updated successfully.")
            except Category.DoesNotExist:
                messages.error(request, "Category not found.")
            return redirect('admin_categories')

        elif action == "upload_image":
            category_id = request.POST.get('category_id')
            try:
                cat = Category.objects.get(id=category_id)
                if request.FILES.get('image'):
                    cat.image = request.FILES.get('image')
                    cat.save()
                    messages.success(request, f"Image uploaded for category '{cat.name}'.")
                else:
                    messages.error(request, "Please select an image file to upload.")
            except Category.DoesNotExist:
                messages.error(request, "Category not found.")
            return redirect('admin_categories')

        elif action == "delete_category":
            category_id = request.POST.get('category_id')
            try:
                cat = Category.objects.get(id=category_id)
                cat_name = cat.name
                product_count = cat.products.count()
                subcat_count = cat.subcategories.count()
                if product_count > 0 or subcat_count > 0:
                    messages.error(request, f"Cannot delete '{cat_name}' — it has {subcat_count} sub-category(ies) and {product_count} product(s). Delete or reassign them first.")
                else:
                    cat.delete()
                    messages.success(request, f"Category '{cat_name}' deleted successfully.")
            except Category.DoesNotExist:
                messages.error(request, "Category not found.")
            return redirect('admin_categories')

        elif action == "toggle_active":
            category_id = request.POST.get('category_id')
            try:
                cat = Category.objects.get(id=category_id)
                cat.is_active = not cat.is_active
                cat.save()
                status_label = "activated" if cat.is_active else "deactivated"
                messages.success(request, f"Category '{cat.name}' {status_label}.")
            except Category.DoesNotExist:
                messages.error(request, "Category not found.")
            return redirect('admin_categories')

        # ── Sub-Category Actions ──
        elif action == "add_subcategory":
            category_id = request.POST.get('category_id')
            sub_name = request.POST.get('name', '').strip()
            sub_code = request.POST.get('code', '').strip()
            description = request.POST.get('description', '').strip()
            display_order = int(request.POST.get('display_order', 0) or 0)
            image = request.FILES.get('image')

            category = Category.objects.filter(id=category_id).first()
            if not category:
                messages.error(request, "Parent category is required.")
            elif not sub_name or not sub_code:
                messages.error(request, "Sub-Category Name and Code are required.")
            elif SubCategory.objects.filter(category=category, code=sub_code.upper()).exists():
                messages.error(request, f"Sub-Category code '{sub_code.upper()}' already exists under '{category.name}'.")
            else:
                sub = SubCategory.objects.create(
                    category=category,
                    name=sub_name,
                    code=sub_code.upper(),
                    description=description,
                    display_order=display_order,
                )
                if image:
                    sub.image = image
                    sub.save()
                messages.success(request, f"Sub-Category '{sub_name}' added under '{category.name}'.")
            return redirect('admin_categories')

        elif action == "update_subcategory":
            subcategory_id = request.POST.get('subcategory_id')
            try:
                sub = SubCategory.objects.get(id=subcategory_id)
                sub.name = request.POST.get('name', sub.name).strip()
                sub.description = request.POST.get('description', sub.description or '').strip()
                sub.display_order = int(request.POST.get('display_order', sub.display_order) or 0)
                cat_id = request.POST.get('category_id')
                if cat_id:
                    new_cat = Category.objects.filter(id=cat_id).first()
                    if new_cat:
                        sub.category = new_cat
                if request.FILES.get('image'):
                    sub.image = request.FILES.get('image')
                sub.save()
                messages.success(request, f"Sub-Category '{sub.name}' updated successfully.")
            except SubCategory.DoesNotExist:
                messages.error(request, "Sub-Category not found.")
            return redirect('admin_categories')

        elif action == "upload_subcategory_image":
            subcategory_id = request.POST.get('subcategory_id')
            try:
                sub = SubCategory.objects.get(id=subcategory_id)
                if request.FILES.get('image'):
                    sub.image = request.FILES.get('image')
                    sub.save()
                    messages.success(request, f"Image uploaded for sub-category '{sub.name}'.")
                else:
                    messages.error(request, "Please select an image file to upload.")
            except SubCategory.DoesNotExist:
                messages.error(request, "Sub-Category not found.")
            return redirect('admin_categories')

        elif action == "delete_subcategory":
            subcategory_id = request.POST.get('subcategory_id')
            try:
                sub = SubCategory.objects.get(id=subcategory_id)
                sub_name = sub.name
                product_count = sub.products.count()
                if product_count > 0:
                    messages.error(request, f"Cannot delete '{sub_name}' — it has {product_count} product(s). Reassign or delete products first.")
                else:
                    sub.delete()
                    messages.success(request, f"Sub-Category '{sub_name}' deleted successfully.")
            except SubCategory.DoesNotExist:
                messages.error(request, "Sub-Category not found.")
            return redirect('admin_categories')

        elif action == "toggle_subcategory_active":
            subcategory_id = request.POST.get('subcategory_id')
            try:
                sub = SubCategory.objects.get(id=subcategory_id)
                sub.is_active = not sub.is_active
                sub.save()
                status_label = "activated" if sub.is_active else "deactivated"
                messages.success(request, f"Sub-Category '{sub.name}' {status_label}.")
            except SubCategory.DoesNotExist:
                messages.error(request, "Sub-Category not found.")
            return redirect('admin_categories')

    categories = Category.objects.prefetch_related('subcategories', 'products').all().order_by('display_order', 'name')
    for cat in categories:
        cat.product_count = cat.products.filter(is_active=True).count()
        cat.subcat_count = cat.subcategories.filter(is_active=True).count()

    total_subcategories = SubCategory.objects.count()

    context = {
        'categories': categories,
        'total_categories': categories.count(),
        'total_subcategories': total_subcategories,
        'active_tab': 'categories',
        'page_title': 'Categories & Product Categories Management',
        'breadcrumbs': [
            {'name': 'Categories', 'url': ''}
        ]
    }
    return render(request, "admin/categories.html", context)



def admin_stores(request):
    """Dedicated Stores Management Page: Add, List, Update, Delete Stores."""
    if not request.user.is_authenticated:
        return redirect('signin')

    if request.method == "POST":
        action = request.POST.get('action')

        if action == "add_store":
            name = request.POST.get('name', '').strip()
            code = request.POST.get('code', '').strip()
            address = request.POST.get('address', '').strip()
            city = request.POST.get('city', '').strip()
            state = request.POST.get('state', '').strip()
            contact_person = request.POST.get('contact_person', '').strip()
            contact_phone = request.POST.get('contact_phone', '').strip()

            if not name or not code:
                messages.error(request, "Store Name and Store Code are required.")
            elif Store.objects.filter(code=code).exists():
                messages.error(request, f"Store code '{code}' already exists.")
            else:
                Store.objects.create(
                    name=name,
                    code=code.upper(),
                    address=address,
                    city=city,
                    state=state,
                    contact_person=contact_person,
                    contact_phone=contact_phone
                )
                messages.success(request, f"Store '{name}' registered successfully.")
            return redirect('admin_stores')

        elif action == "update_store":
            store_id = request.POST.get('store_id')
            try:
                store = Store.objects.get(id=store_id)
                store.name = request.POST.get('name', store.name).strip()
                store.city = request.POST.get('city', store.city).strip()
                store.state = request.POST.get('state', store.state).strip()
                store.contact_person = request.POST.get('contact_person', store.contact_person).strip()
                store.contact_phone = request.POST.get('contact_phone', store.contact_phone).strip()
                store.save()
                messages.success(request, f"Store '{store.name}' updated successfully.")
            except Store.DoesNotExist:
                messages.error(request, "Store not found.")
            return redirect('admin_stores')

        elif action == "delete_store":
            store_id = request.POST.get('store_id')
            try:
                store = Store.objects.get(id=store_id)
                store.delete()
                messages.success(request, "Store deleted successfully.")
            except Store.DoesNotExist:
                messages.error(request, "Store not found.")
            return redirect('admin_stores')

    stores = Store.objects.prefetch_related('kiosks', 'assigned_managers').filter(is_active=True).order_by('name')

    context = {
        'stores': stores,
        'total_stores': stores.count(),
        'active_tab': 'stores',
    }
    return render(request, "admin/stores.html", context)


def admin_store_detail(request, store_id):
    """Single Store Detail View: store details, operational metrics, assigned staff, and connected kiosk devices."""
    if not request.user.is_authenticated:
        return redirect('signin')

    store = get_object_or_404(Store.objects.prefetch_related('assigned_managers'), id=store_id)

    if request.method == "POST":
        action = request.POST.get('action')

        if action == "update_store":
            store.name = request.POST.get('name', store.name).strip()
            store.address = request.POST.get('address', store.address).strip()
            store.city = request.POST.get('city', store.city).strip()
            store.state = request.POST.get('state', store.state).strip()
            store.country = request.POST.get('country', store.country).strip()
            store.contact_person = request.POST.get('contact_person', store.contact_person).strip()
            store.contact_phone = request.POST.get('contact_phone', store.contact_phone).strip()
            store.save()
            messages.success(request, f"Store '{store.name}' updated successfully.")
            return redirect('admin_store_detail', store_id=store.id)

        elif action == "assign_kiosk":
            kiosk_id = request.POST.get('kiosk_id')
            if kiosk_id:
                try:
                    kiosk = KioskDevice.objects.get(id=kiosk_id)
                    kiosk.store = store
                    kiosk.save()
                    messages.success(request, f"Kiosk '{kiosk.name}' assigned to {store.name}.")
                except KioskDevice.DoesNotExist:
                    messages.error(request, "Kiosk device not found.")
            return redirect('admin_store_detail', store_id=store.id)

        elif action == "unassign_kiosk":
            kiosk_id = request.POST.get('kiosk_id')
            if kiosk_id:
                try:
                    kiosk = KioskDevice.objects.get(id=kiosk_id, store=store)
                    kiosk.store = None
                    kiosk.save()
                    messages.success(request, f"Kiosk '{kiosk.name}' unassigned from {store.name}.")
                except KioskDevice.DoesNotExist:
                    messages.error(request, "Kiosk device not found in this store.")
            return redirect('admin_store_detail', store_id=store.id)

    # Fetch connected kiosks
    connected_kiosks = KioskDevice.objects.filter(store=store).select_related('profile').order_by('name')

    online_count = 0
    warning_count = 0
    offline_count = 0
    disabled_count = 0
    kiosk_list = []

    for k in connected_kiosks:
        status = update_kiosk_status_and_alerts(k)
        is_online = (status == KioskDevice.Status.ONLINE)
        if status == KioskDevice.Status.ONLINE:
            online_count += 1
        elif status == KioskDevice.Status.WARNING:
            warning_count += 1
        elif status == KioskDevice.Status.DISABLED:
            disabled_count += 1
        else:
            offline_count += 1

        kiosk_list.append({
            'kiosk': k,
            'status': status,
            'is_online': is_online,
        })

    # Fetch unassigned kiosks that can be assigned to this store
    unassigned_kiosks = KioskDevice.objects.filter(store__isnull=True, is_active=True).order_by('name')

    # Fetch assigned managers
    assigned_managers = store.assigned_managers.all()

    context = {
        'store': store,
        'connected_kiosks': kiosk_list,
        'unassigned_kiosks': unassigned_kiosks,
        'total_kiosks': len(kiosk_list),
        'online_count': online_count,
        'warning_count': warning_count,
        'offline_count': offline_count,
        'disabled_count': disabled_count,
        'assigned_managers': assigned_managers,
        'active_tab': 'stores',
        'page_title': f'Store Details: {store.name}',
        'breadcrumbs': [
            {'name': 'Stores Directory', 'url': '/admin_pannel/stores/'},
            {'name': f'Store Details ({store.code})', 'url': ''}
        ]
    }
    return render(request, "admin/store_detail.html", context)


def admin_users(request):
    """Dedicated User & Staff Management Page: Add Users, Edit Roles, Assign Stores, Disable."""
    if not request.user.is_authenticated:
        return redirect('signin')

    if request.method == "POST":
        action = request.POST.get('action')

        if action == "add_user":
            username = request.POST.get('username', '').strip()
            email = request.POST.get('email', '').strip()
            password = request.POST.get('password', '')
            role = request.POST.get('role', User.Role.ADMIN)
            assigned_store_ids = request.POST.getlist('assigned_stores')

            if not username or not password:
                messages.error(request, "Username and Password are required.")
            elif User.objects.filter(username=username).exists():
                messages.error(request, f"Username '{username}' is already taken.")
            else:
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    role=role
                )
                if role == User.Role.SUPER_ADMIN or role == User.Role.ADMIN:
                    user.is_staff = True
                    user.save()

                if assigned_store_ids:
                    stores = Store.objects.filter(id__in=assigned_store_ids)
                    user.assigned_stores.set(stores)

                messages.success(request, f"User [{user.username}] created successfully with role '{user.get_role_display()}'.")
            return redirect('admin_users')

        elif action == "update_user":
            user_id = request.POST.get('user_id')
            role = request.POST.get('role')
            is_active = request.POST.get('is_active') == 'true'
            assigned_store_ids = request.POST.getlist('assigned_stores')

            try:
                user = User.objects.get(id=user_id)
                user.role = role
                user.is_active = is_active
                if role in [User.Role.SUPER_ADMIN, User.Role.ADMIN]:
                    user.is_staff = True
                user.save()

                if assigned_store_ids:
                    stores = Store.objects.filter(id__in=assigned_store_ids)
                    user.assigned_stores.set(stores)
                else:
                    user.assigned_stores.clear()

                messages.success(request, f"User '{user.username}' updated successfully.")
            except User.DoesNotExist:
                messages.error(request, "User not found.")
            return redirect('admin_users')

        elif action == "delete_user":
            user_id = request.POST.get('user_id')
            try:
                user = User.objects.get(id=user_id)
                if user == request.user:
                    messages.error(request, "You cannot delete your own logged-in user account.")
                else:
                    user.delete()
                    messages.success(request, "User deleted successfully.")
            except User.DoesNotExist:
                messages.error(request, "User not found.")
            return redirect('admin_users')

    users = User.objects.prefetch_related('assigned_stores').all().order_by('-date_joined')
    stores = Store.objects.filter(is_active=True).order_by('name')

    context = {
        'users': users,
        'roles': User.Role.choices,
        'stores': stores,
        'total_users': users.count(),
        'active_tab': 'users',
    }
    return render(request, "admin/users.html", context)


def admin_monitoring(request):
    """Dedicated Kiosk Telemetry Hub Page: Live pings, Heartbeat stream & Alerts."""
    if not request.user.is_authenticated:
        return redirect('signin')

    kiosks = KioskDevice.objects.select_related('store', 'profile').all().order_by('-created_at')
    now = timezone.now()
    kiosk_list = []
    online_count = 0
    warning_count = 0
    offline_count = 0

    for k in kiosks:
        status = update_kiosk_status_and_alerts(k)
        is_online = (status == KioskDevice.Status.ONLINE)
        if status == KioskDevice.Status.ONLINE:
            online_count += 1
        elif status == KioskDevice.Status.WARNING:
            warning_count += 1
        else:
            offline_count += 1

        heartbeat_age_seconds = None
        heartbeat_display = "No Heartbeat (Offline)"
        if k.last_heartbeat_at:
            heartbeat_age_seconds = int((now - k.last_heartbeat_at).total_seconds())
            if heartbeat_age_seconds < 10:
                heartbeat_display = f"{heartbeat_age_seconds}s ago"
            elif heartbeat_age_seconds < 60:
                heartbeat_display = f"{heartbeat_age_seconds}s ago"
            elif heartbeat_age_seconds < 3600:
                heartbeat_display = f"{heartbeat_age_seconds // 60}m ago"
            else:
                heartbeat_display = k.last_heartbeat_at.strftime('%Y-%m-%d %H:%M')

        kiosk_list.append({
            'id': str(k.id),
            'username': k.name,
            'device_id': k.device_id,
            'location': k.store.name if k.store else 'Unspecified Location',
            'status': status,
            'is_online': is_online,
            'heartbeat_age_seconds': heartbeat_age_seconds,
            'heartbeat_display': heartbeat_display,
            'battery_percentage': k.battery_percentage,
            'network_type': k.network_type or 'WIFI',
            'last_ip_address': k.last_ip_address or '—',
            'last_sync': k.last_sync_at.strftime('%Y-%m-%d %H:%M:%S') if k.last_sync_at else 'Never Synced',
            'app_version': k.app_version or 'v1.0.0',
            'device_info': f"{k.manufacturer or ''} {k.device_model or ''}".strip() or 'Android Display',
            'last_boot': k.last_seen_at.strftime('%Y-%m-%d %H:%M:%S') if k.last_seen_at else 'N/A',
            'latitude': str(k.latitude) if k.latitude is not None else None,
            'longitude': str(k.longitude) if k.longitude is not None else None,
            'has_location': (k.latitude is not None and k.longitude is not None),
        })

    open_alerts = Alert.objects.filter(resolved_at__isnull=True).select_related('kiosk')[:20]
    recent_events = KioskEvent.objects.select_related('kiosk').order_by('-created_at')[:30]

    context = {
        'kiosks': kiosk_list,
        'open_alerts': open_alerts,
        'recent_events': recent_events,
        'online_count': online_count,
        'warning_count': warning_count,
        'offline_count': offline_count,
        'total_count': len(kiosk_list),
        'active_tab': 'monitoring',
    }
    return render(request, "admin/monitoring.html", context)


def admin_monitoring_kiosk_detail(request, kiosk_id):
    """Dedicated Live Telemetry & Hardware Monitoring Inspector for a single kiosk."""
    if not request.user.is_authenticated:
        return redirect('signin')

    kiosk = get_object_or_404(KioskDevice.objects.select_related('store', 'profile'), id=kiosk_id)
    status = update_kiosk_status_and_alerts(kiosk)
    now = timezone.now()

    heartbeat_age_seconds = None
    heartbeat_display = "No Heartbeat (Offline)"
    if kiosk.last_heartbeat_at:
        heartbeat_age_seconds = int((now - kiosk.last_heartbeat_at).total_seconds())
        if heartbeat_age_seconds < 10:
            heartbeat_display = f"{heartbeat_age_seconds}s ago"
        elif heartbeat_age_seconds < 60:
            heartbeat_display = f"{heartbeat_age_seconds}s ago"
        elif heartbeat_age_seconds < 3600:
            heartbeat_display = f"{heartbeat_age_seconds // 60}m ago"
        else:
            heartbeat_display = kiosk.last_heartbeat_at.strftime('%Y-%m-%d %H:%M:%S')

    recent_events = KioskEvent.objects.filter(kiosk=kiosk).order_by('-created_at')[:40]
    open_alerts = Alert.objects.filter(kiosk=kiosk, resolved_at__isnull=True).order_by('-opened_at')
    resolved_alerts = Alert.objects.filter(kiosk=kiosk, resolved_at__isnull=False).order_by('-resolved_at')[:15]

    context = {
        'kiosk': kiosk,
        'status': status,
        'is_online': (status == KioskDevice.Status.ONLINE),
        'heartbeat_age_seconds': heartbeat_age_seconds,
        'heartbeat_display': heartbeat_display,
        'recent_events': recent_events,
        'open_alerts': open_alerts,
        'resolved_alerts': resolved_alerts,
        'active_tab': 'monitoring',
        'page_title': f'Live Telemetry Inspector: {kiosk.name}',
        'breadcrumbs': [
            {'name': 'Telemetry Hub', 'url': '/admin_pannel/monitoring/'},
            {'name': f'Monitoring Node ({kiosk.device_id})', 'url': ''}
        ]
    }
    return render(request, "admin/monitoring_detail.html", context)


def admin_monitoring_live_status(request):
    """JSON API endpoint returning real-time status and telemetry for live dashboard auto-refresh."""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    kiosks = KioskDevice.objects.select_related('store').all().order_by('-created_at')
    now = timezone.now()
    kiosk_data = []

    for k in kiosks:
        status = update_kiosk_status_and_alerts(k)
        heartbeat_age_seconds = None
        heartbeat_display = "No Heartbeat"
        if k.last_heartbeat_at:
            heartbeat_age_seconds = int((now - k.last_heartbeat_at).total_seconds())
            if heartbeat_age_seconds < 60:
                heartbeat_display = f"{heartbeat_age_seconds}s ago"
            else:
                heartbeat_display = f"{heartbeat_age_seconds // 60}m ago"

        kiosk_data.append({
            'id': str(k.id),
            'name': k.name,
            'device_id': k.device_id,
            'location': k.store.name if k.store else 'Unspecified Location',
            'status': status,
            'is_online': (status == KioskDevice.Status.ONLINE),
            'heartbeat_age_seconds': heartbeat_age_seconds,
            'heartbeat_display': heartbeat_display,
            'battery_percentage': k.battery_percentage,
            'network_type': k.network_type or 'WIFI',
            'last_ip_address': k.last_ip_address or '—',
            'app_version': k.app_version or 'v1.0.0',
            'latitude': str(k.latitude) if k.latitude is not None else None,
            'longitude': str(k.longitude) if k.longitude is not None else None,
            'has_location': (k.latitude is not None and k.longitude is not None),
        })


    recent_events_qs = KioskEvent.objects.select_related('kiosk').order_by('-created_at')[:20]
    events_data = []
    for ev in recent_events_qs:
        events_data.append({
            'kiosk_name': ev.kiosk.name,
            'kiosk_device_id': ev.kiosk.device_id,
            'event_type': ev.event_type,
            'severity': ev.severity,
            'message': ev.message,
            'time': ev.created_at.strftime('%H:%M:%S'),
        })

    open_alerts_count = Alert.objects.filter(resolved_at__isnull=True).count()

    return JsonResponse({
        'success': True,
        'server_time': now.strftime('%H:%M:%S'),
        'kiosks': kiosk_data,
        'recent_events': events_data,
        'open_alerts_count': open_alerts_count,
    })



def admin_media(request):
    """Dedicated Media Assets Manager Page: Upload & Manage Videos, PDFs, Tech Specs."""
    if not request.user.is_authenticated:
        return redirect('signin')

    if request.method == "POST":
        action = request.POST.get('action')

        if action == "upload_media":
            title = request.POST.get('title', '').strip()
            asset_type = request.POST.get('asset_type', MediaAsset.AssetType.VIDEO)
            profile_id = request.POST.get('profile_id', '').strip()
            external_url = request.POST.get('external_url', '').strip()
            file = request.FILES.get('file')

            if not title:
                messages.error(request, "Media title is required.")
            else:
                profile = KioskProfile.objects.filter(id=profile_id).first() if profile_id else None
                file_size = round(file.size / (1024 * 1024), 2) if file else 0.0
                MediaAsset.objects.create(
                    title=title,
                    asset_type=asset_type,
                    file=file,
                    external_url=external_url,
                    file_size_mb=file_size,
                    kiosk_profile=profile
                )
                messages.success(request, f"Media asset '{title}' uploaded successfully.")
            return redirect('admin_media')

        elif action == "delete_media":
            asset_id = request.POST.get('asset_id')
            try:
                asset = MediaAsset.objects.get(id=asset_id)
                asset.delete()
                messages.success(request, "Media asset deleted.")
            except MediaAsset.DoesNotExist:
                messages.error(request, "Media asset not found.")
            return redirect('admin_media')

    media_items = MediaAsset.objects.select_related('kiosk_profile').filter(is_active=True).order_by('-created_at')
    profiles = KioskProfile.objects.filter(is_active=True).order_by('name')

    context = {
        'media_items': media_items,
        'profiles': profiles,
        'total_media': media_items.count(),
        'asset_types': MediaAsset.AssetType.choices,
        'active_tab': 'media',
    }
    return render(request, "admin/media.html", context)


def admin_profile(request):
    """View and update current logged-in user profile details."""
    if not request.user.is_authenticated:
        return redirect('signin')

    user = request.user
    if request.method == "POST":
        email = request.POST.get('email', '').strip()
        new_password = request.POST.get('password', '')

        user.email = email
        if new_password:
            user.set_password(new_password)
            user.save()
            from django.contrib.auth import update_session_auth_hash
            update_session_auth_hash(request, user)
            messages.success(request, "Password and profile details updated successfully.")
        else:
            user.save()
            messages.success(request, "Profile details updated successfully.")
        return redirect('admin_profile')

    context = {
        'profile_user': user,
        'active_tab': 'profile',
        'breadcrumbs': [{'name': 'Profile Settings', 'url': ''}]
    }
    return render(request, "admin/profile.html", context)


def admin_settings(request):
    """View and adjust CMS System & Kiosk Global Configuration Settings."""
    if not request.user.is_authenticated:
        return redirect('signin')

    if request.method == "POST":
        messages.success(request, "System configuration settings updated successfully.")
        return redirect('admin_settings')

    context = {
        'active_tab': 'settings',
        'breadcrumbs': [{'name': 'System Settings', 'url': ''}]
    }
    return render(request, "admin/settings.html", context)


def admin_screensavers(request):
    """Screensavers Management Page: List, Filter, Search, Interactive Slide Simulation Player."""
    if not request.user.is_authenticated:
        return redirect('signin')

    if request.method == "POST":
        action = request.POST.get('action')
        if action == "delete_screensaver":
            screensaver_id = request.POST.get('screensaver_id')
            ss = get_object_or_404(Screensaver, id=screensaver_id)
            title = ss.title
            ss.delete()
            messages.success(request, f"Screensaver '{title}' deleted successfully.")
            return redirect('admin_screensavers')
        elif action == "toggle_active":
            screensaver_id = request.POST.get('screensaver_id')
            ss = get_object_or_404(Screensaver, id=screensaver_id)
            ss.is_active = not ss.is_active
            ss.save(update_fields=['is_active'])
            status_label = "activated" if ss.is_active else "deactivated"
            messages.success(request, f"Screensaver '{ss.title}' has been {status_label}.")
            return redirect('admin_screensavers')

    # Query filtering
    orientation = request.GET.get('orientation', '').upper()
    status_filter = request.GET.get('status', '')
    profile_id = request.GET.get('profile_id', '')
    search_query = request.GET.get('q', '').strip()

    screensavers = Screensaver.objects.select_related('kiosk_profile').all()

    if orientation in ['LANDSCAPE', 'PORTRAIT', 'BOTH']:
        screensavers = screensavers.filter(orientation=orientation)
    if status_filter == 'active':
        screensavers = screensavers.filter(is_active=True)
    elif status_filter == 'inactive':
        screensavers = screensavers.filter(is_active=False)
    if profile_id:
        screensavers = screensavers.filter(kiosk_profile_id=profile_id)
    if search_query:
        screensavers = screensavers.filter(
            Q(title__icontains=search_query) | Q(caption__icontains=search_query) | Q(description__icontains=search_query)
        )

    all_screensavers = Screensaver.objects.all()
    total_screensavers = all_screensavers.count()
    landscape_count = all_screensavers.filter(orientation='LANDSCAPE').count()
    portrait_count = all_screensavers.filter(orientation='PORTRAIT').count()
    both_count = all_screensavers.filter(orientation='BOTH').count()
    active_count = all_screensavers.filter(is_active=True).count()

    profiles = KioskProfile.objects.filter(is_active=True)

    # Convert screensavers to JSON structure for real-time live sliding simulator modal
    active_slides = []
    for s in all_screensavers.order_by('display_order', '-created_at'):
        active_slides.append({
            'id': str(s.id),
            'title': s.title,
            'image_url': s.image.url if s.image else '',
            'orientation': s.orientation,
            'duration': s.duration_seconds,
            'caption': s.caption or '',
            'is_active': s.is_active,
            'profile_name': s.kiosk_profile.name if s.kiosk_profile else 'All Profiles'
        })


    context = {
        'screensavers': screensavers,
        'total_screensavers': total_screensavers,
        'landscape_count': landscape_count,
        'portrait_count': portrait_count,
        'both_count': both_count,
        'active_count': active_count,
        'profiles': profiles,
        'active_slides_json': json.dumps(active_slides),
        'current_orientation': orientation,
        'current_status': status_filter,
        'current_profile': profile_id,
        'search_query': search_query,
        'active_tab': 'screensavers',
        'breadcrumbs': [{'name': 'Screensavers', 'url': ''}]
    }
    return render(request, "admin/screensavers.html", context)


def admin_screensaver_add(request):
    """Add a new Screensaver view."""
    if not request.user.is_authenticated:
        return redirect('signin')

    if request.method == "POST":
        title = request.POST.get('title', '').strip()
        orientation = request.POST.get('orientation', 'LANDSCAPE')
        duration_seconds = request.POST.get('duration_seconds', '10')
        display_order = request.POST.get('display_order', '0')
        caption = request.POST.get('caption', '').strip()
        description = request.POST.get('description', '').strip()
        profile_id = request.POST.get('profile_id', '').strip()
        is_active = request.POST.get('is_active') in ['true', 'on', '1']
        image_file = request.FILES.get('image')

        if not title:
            messages.error(request, "Screensaver title is required.")
        elif not image_file:
            messages.error(request, "Please upload a screensaver image.")
        else:
            try:
                duration_seconds = int(duration_seconds)
            except ValueError:
                duration_seconds = 10

            try:
                display_order = int(display_order)
            except ValueError:
                display_order = 0

            profile = None
            if profile_id:
                try:
                    profile = KioskProfile.objects.get(id=profile_id)
                except KioskProfile.DoesNotExist:
                    pass

            screensaver = Screensaver.objects.create(
                title=title,
                image=image_file,
                orientation=orientation,
                duration_seconds=duration_seconds,
                display_order=display_order,
                caption=caption,
                description=description,
                kiosk_profile=profile,
                is_active=is_active
            )
            messages.success(request, f"Screensaver '{screensaver.title}' added successfully.")
            return redirect('admin_screensavers')

    profiles = KioskProfile.objects.filter(is_active=True)
    context = {
        'profiles': profiles,
        'active_tab': 'screensavers',
        'breadcrumbs': [
            {'name': 'Screensavers', 'url': '/admin_pannel/screensavers/'},
            {'name': 'Add Screensaver', 'url': ''}
        ]
    }
    return render(request, "admin/screensaver_add.html", context)


def admin_screensaver_detail(request, screensaver_id):
    """View Single Screensaver Detail Page."""
    if not request.user.is_authenticated:
        return redirect('signin')

    screensaver = get_object_or_404(Screensaver.objects.select_related('kiosk_profile'), id=screensaver_id)
    
    context = {
        'screensaver': screensaver,
        'active_tab': 'screensavers',
        'breadcrumbs': [
            {'name': 'Screensavers', 'url': '/admin_pannel/screensavers/'},
            {'name': screensaver.title, 'url': ''}
        ]
    }
    return render(request, "admin/screensaver_detail.html", context)


def admin_screensaver_edit(request, screensaver_id):
    """Edit existing Screensaver view."""
    if not request.user.is_authenticated:
        return redirect('signin')

    screensaver = get_object_or_404(Screensaver, id=screensaver_id)

    if request.method == "POST":
        title = request.POST.get('title', '').strip()
        orientation = request.POST.get('orientation', 'LANDSCAPE')
        duration_seconds = request.POST.get('duration_seconds', '10')
        display_order = request.POST.get('display_order', '0')
        caption = request.POST.get('caption', '').strip()
        description = request.POST.get('description', '').strip()
        profile_id = request.POST.get('profile_id', '').strip()
        is_active = request.POST.get('is_active') in ['true', 'on', '1']
        new_image = request.FILES.get('image')

        if not title:
            messages.error(request, "Screensaver title cannot be empty.")
        else:
            screensaver.title = title
            screensaver.orientation = orientation
            try:
                screensaver.duration_seconds = int(duration_seconds)
            except ValueError:
                pass
            try:
                screensaver.display_order = int(display_order)
            except ValueError:
                pass
            screensaver.caption = caption
            screensaver.description = description
            screensaver.is_active = is_active

            if profile_id:
                try:
                    screensaver.kiosk_profile = KioskProfile.objects.get(id=profile_id)
                except KioskProfile.DoesNotExist:
                    screensaver.kiosk_profile = None
            else:
                screensaver.kiosk_profile = None

            if new_image:
                screensaver.image = new_image

            screensaver.save()
            messages.success(request, f"Screensaver '{screensaver.title}' updated successfully.")
            return redirect('admin_screensaver_detail', screensaver_id=screensaver.id)

    profiles = KioskProfile.objects.filter(is_active=True)
    context = {
        'screensaver': screensaver,
        'profiles': profiles,
        'active_tab': 'screensavers',
        'breadcrumbs': [
            {'name': 'Screensavers', 'url': '/admin_pannel/screensavers/'},
            {'name': screensaver.title, 'url': f'/admin_pannel/screensavers/{screensaver.id}/'},
            {'name': 'Edit', 'url': ''}
        ]
    }
    return render(request, "admin/screensaver_edit.html", context)


def admin_screensaver_delete(request, screensaver_id):
    """Delete screensaver view."""
    if not request.user.is_authenticated:
        return redirect('signin')

    screensaver = get_object_or_404(Screensaver, id=screensaver_id)
    title = screensaver.title
    screensaver.delete()
    messages.success(request, f"Screensaver '{title}' deleted successfully.")
    return redirect('admin_screensavers')


def admin_screensaver_toggle_active(request, screensaver_id):
    """Toggle screensaver active state view."""
    if not request.user.is_authenticated:
        return redirect('signin')

    screensaver = get_object_or_404(Screensaver, id=screensaver_id)
    screensaver.is_active = not screensaver.is_active
    screensaver.save(update_fields=['is_active'])
    status_label = "activated" if screensaver.is_active else "deactivated"
    messages.success(request, f"Screensaver '{screensaver.title}' has been {status_label}.")
    return redirect(request.META.get('HTTP_REFERER', 'admin_screensavers'))


def admin_analytics(request):
    """
    Kiosk Click Analytics & Device Usage Frequency Dashboard.
    Provides deep insights into product engagement, most clicked products,
    hourly usage frequency distribution, and per-kiosk device engagement.
    """
    if not request.user.is_authenticated:
        return redirect('signin')

    period = request.GET.get('period', '7d')
    selected_kiosk_id = request.GET.get('kiosk_id', '').strip()
    selected_store_id = request.GET.get('store_id', '').strip()

    now = timezone.now()
    if period == 'today':
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        period_label = "Today"
    elif period == '30d':
        start_date = now - timedelta(days=30)
        period_label = "Last 30 Days"
    elif period == '90d':
        start_date = now - timedelta(days=90)
        period_label = "Last 90 Days"
    elif period == 'all':
        start_date = None
        period_label = "All Time"
    else:  # default '7d'
        period = '7d'
        start_date = now - timedelta(days=7)
        period_label = "Last 7 Days"

    # Base QuerySets
    interactions_qs = ProductInteraction.objects.select_related('kiosk', 'product', 'product__category')
    sessions_qs = KioskUsageSession.objects.select_related('kiosk', 'kiosk__store')

    if start_date:
        interactions_qs = interactions_qs.filter(created_at__gte=start_date)
        sessions_qs = sessions_qs.filter(started_at__gte=start_date)

    if selected_kiosk_id:
        interactions_qs = interactions_qs.filter(kiosk_id=selected_kiosk_id)
        sessions_qs = sessions_qs.filter(kiosk_id=selected_kiosk_id)

    if selected_store_id:
        interactions_qs = interactions_qs.filter(kiosk__store_id=selected_store_id)
        sessions_qs = sessions_qs.filter(kiosk__store_id=selected_store_id)

    # 1. Summary KPI Metrics
    total_interactions = interactions_qs.count()
    total_clicks = interactions_qs.filter(
        interaction_type__in=[
            ProductInteraction.InteractionType.CLICK,
            ProductInteraction.InteractionType.VIEW_DETAIL,
            ProductInteraction.InteractionType.SEARCH_SELECT
        ]
    ).count()
    total_sessions = sessions_qs.count()

    avg_dur = sessions_qs.aggregate(avg=Avg('duration_seconds'))['avg'] or 0
    avg_duration_minutes = int(avg_dur // 60)
    avg_duration_seconds = int(avg_dur % 60)
    avg_duration_display = f"{avg_duration_minutes}m {avg_duration_seconds:02d}s" if avg_duration_minutes > 0 else f"{avg_duration_seconds}s"

    active_kiosks_count = sessions_qs.values('kiosk').distinct().count()

    top_product_row = (
        interactions_qs
        .filter(product__isnull=False)
        .values('product__name', 'product__sku')
        .annotate(cnt=Count('id'))
        .order_by('-cnt')
        .first()
    )
    top_product_name = top_product_row['product__name'] if top_product_row else 'None recorded'
    top_product_count = top_product_row['cnt'] if top_product_row else 0

    top_kiosk_row = (
        sessions_qs
        .values('kiosk__name', 'kiosk__device_id')
        .annotate(cnt=Count('id'))
        .order_by('-cnt')
        .first()
    )
    top_kiosk_name = (top_kiosk_row['kiosk__name'] or top_kiosk_row['kiosk__device_id']) if top_kiosk_row else 'None recorded'
    top_kiosk_sessions = top_kiosk_row['cnt'] if top_kiosk_row else 0

    # 2. Most Frequently Clicked Products Leaderboard
    product_clicks_query = (
        interactions_qs
        .filter(product__isnull=False)
        .values(
            'product__id',
            'product__name',
            'product__sku',
            'product__category__name',
            'product__image',
            'product__price'
        )
        .annotate(
            card_clicks=Count('id', filter=Q(interaction_type=ProductInteraction.InteractionType.CLICK)),
            detail_views=Count('id', filter=Q(interaction_type=ProductInteraction.InteractionType.VIEW_DETAIL)),
            spec_tab_clicks=Count('id', filter=Q(interaction_type=ProductInteraction.InteractionType.SPEC_TAB_CLICK)),
            brochure_views=Count('id', filter=Q(interaction_type=ProductInteraction.InteractionType.BROCHURE_VIEW)),
            total_interactions=Count('id'),
            unique_kiosks=Count('kiosk', distinct=True)
        )
        .order_by('-total_interactions')[:30]
    )

    top_products = []
    max_interactions = product_clicks_query[0]['total_interactions'] if product_clicks_query else 1
    for rank, p in enumerate(product_clicks_query, start=1):
        percent = round((p['total_interactions'] / max_interactions) * 100, 1) if max_interactions > 0 else 0
        top_products.append({
            'rank': rank,
            'id': p['product__id'],
            'name': p['product__name'],
            'sku': p['product__sku'],
            'category_name': p['product__category__name'] or 'Uncategorized',
            'image': p['product__image'],
            'price': p['product__price'],
            'card_clicks': p['card_clicks'],
            'detail_views': p['detail_views'],
            'spec_tab_clicks': p['spec_tab_clicks'],
            'brochure_views': p['brochure_views'],
            'total_interactions': p['total_interactions'],
            'unique_kiosks': p['unique_kiosks'],
            'popularity_percent': percent,
        })

    # 3. Kiosk Device Usage Frequency & Engagement Breakdown
    all_kiosks = KioskDevice.objects.select_related('store', 'profile').all()
    kiosk_usage_list = []
    total_device_clicks = 0
    total_device_sessions = 0

    for k in all_kiosks:
        k_sessions = sessions_qs.filter(kiosk=k)
        sess_cnt = k_sessions.count()
        k_interactions = interactions_qs.filter(kiosk=k)
        clk_cnt = k_interactions.count()
        dur_avg = k_sessions.aggregate(avg=Avg('duration_seconds'))['avg'] or 0
        dur_m = int(dur_avg // 60)
        dur_s = int(dur_avg % 60)
        dur_display = f"{dur_m}m {dur_s:02d}s" if dur_m > 0 else f"{dur_s}s"
        last_session = k_sessions.order_by('-started_at').first()

        total_device_clicks += clk_cnt
        total_device_sessions += sess_cnt

        kiosk_usage_list.append({
            'id': str(k.id),
            'name': k.name,
            'device_id': k.device_id,
            'store_name': k.store.name if k.store else 'Unspecified',
            'status': k.status,
            'is_online': (k.status == KioskDevice.Status.ONLINE),
            'session_count': sess_cnt,
            'click_count': clk_cnt,
            'avg_clicks_per_session': round(clk_cnt / sess_cnt, 1) if sess_cnt > 0 else 0,
            'avg_duration_seconds': round(dur_avg, 1),
            'avg_duration_display': dur_display,
            'last_active': last_session.started_at if last_session else k.last_seen_at,
        })

    # Sort kiosks by session frequency
    kiosk_usage_list.sort(key=lambda x: (x['session_count'], x['click_count']), reverse=True)

    # 4. Chart Data Preparation: Peak Usage Hours (00:00 - 23:00)
    hourly_counts_query = (
        interactions_qs
        .annotate(hour=ExtractHour('created_at'))
        .values('hour')
        .annotate(count=Count('id'))
        .order_by('hour')
    )
    hourly_map = {item['hour']: item['count'] for item in hourly_counts_query if item['hour'] is not None}
    hourly_labels = [f"{h:02d}:00" for h in range(24)]
    hourly_data = [hourly_map.get(h, 0) for h in range(24)]

    # 5. Chart Data Preparation: Daily Trends (Interactions & Sessions)
    days_to_track = 30 if period in ['30d', '90d', 'all'] else (1 if period == 'today' else 7)
    trend_labels = []
    trend_clicks = []
    trend_sessions = []

    if period == 'today':
        # Split today by 2-hour blocks
        for h in range(0, 24, 2):
            label = f"{h:02d}:00"
            trend_labels.append(label)
            c = hourly_map.get(h, 0) + hourly_map.get(h + 1, 0)
            trend_clicks.append(c)
            trend_sessions.append(int(c * 0.4))
    else:
        # Generate date series
        date_series = [now.date() - timedelta(days=d) for d in reversed(range(days_to_track))]
        daily_clicks_dict = {
            item['day']: item['cnt']
            for item in interactions_qs.annotate(day=TruncDate('created_at')).values('day').annotate(cnt=Count('id'))
            if item['day']
        }
        daily_sess_dict = {
            item['day']: item['cnt']
            for item in sessions_qs.annotate(day=TruncDate('started_at')).values('day').annotate(cnt=Count('id'))
            if item['day']
        }
        for d in date_series:
            trend_labels.append(d.strftime('%b %d'))
            trend_clicks.append(daily_clicks_dict.get(d, 0))
            trend_sessions.append(daily_sess_dict.get(d, 0))

    # 6. Chart Data Preparation: Category Popularity
    cat_query = (
        interactions_qs
        .filter(product__category__isnull=False)
        .values('product__category__name')
        .annotate(count=Count('id'))
        .order_by('-count')[:6]
    )
    category_labels = [c['product__category__name'] for c in cat_query]
    category_data = [c['count'] for c in cat_query]

    # Filter dropdown lists
    filter_kiosks = KioskDevice.objects.only('id', 'name', 'device_id').order_by('name')
    filter_stores = Store.objects.filter(is_active=True).only('id', 'name').order_by('name')

    context = {
        'active_tab': 'analytics',
        'period': period,
        'period_label': period_label,
        'selected_kiosk_id': selected_kiosk_id,
        'selected_store_id': selected_store_id,
        'filter_kiosks': filter_kiosks,
        'filter_stores': filter_stores,
        
        # Summary Metrics
        'total_interactions': total_interactions,
        'total_clicks': total_clicks,
        'total_sessions': total_sessions,
        'avg_duration_display': avg_duration_display,
        'active_kiosks_count': active_kiosks_count,
        'top_product_name': top_product_name,
        'top_product_count': top_product_count,
        'top_kiosk_name': top_kiosk_name,
        'top_kiosk_sessions': top_kiosk_sessions,

        # Tables
        'top_products': top_products,
        'kiosk_usage_list': kiosk_usage_list,

        # Chart JSON
        'chart_hourly_labels': json.dumps(hourly_labels),
        'chart_hourly_data': json.dumps(hourly_data),
        'chart_trend_labels': json.dumps(trend_labels),
        'chart_trend_clicks': json.dumps(trend_clicks),
        'chart_trend_sessions': json.dumps(trend_sessions),
        'chart_category_labels': json.dumps(category_labels),
        'chart_category_data': json.dumps(category_data),
    }

    return render(request, "admin/analytics.html", context)


def admin_analytics_export(request):
    """Exports top clicked products report in CSV format."""
    if not request.user.is_authenticated:
        return redirect('signin')

    period = request.GET.get('period', '7d')
    now = timezone.now()
    if period == 'today':
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == '30d':
        start_date = now - timedelta(days=30)
    elif period == 'all':
        start_date = None
    else:
        start_date = now - timedelta(days=7)

    qs = ProductInteraction.objects.filter(product__isnull=False)
    if start_date:
        qs = qs.filter(created_at__gte=start_date)

    aggregated = (
        qs.values('product__name', 'product__sku', 'product__category__name')
        .annotate(
            total_clicks=Count('id', filter=Q(interaction_type=ProductInteraction.InteractionType.CLICK)),
            detail_views=Count('id', filter=Q(interaction_type=ProductInteraction.InteractionType.VIEW_DETAIL)),
            total_events=Count('id'),
            unique_kiosks=Count('kiosk', distinct=True)
        )
        .order_by('-total_events')
    )

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="kiosk_click_analytics_{period}_{now.strftime("%Y%m%d")}.csv"'

    writer = csv.writer(response)
    writer.writerow(['Rank', 'Product Name', 'SKU', 'Category', 'Card Clicks', 'Detail Views', 'Total Events', 'Unique Kiosks'])
    for idx, row in enumerate(aggregated, start=1):
        writer.writerow([
            idx,
            row['product__name'],
            row['product__sku'],
            row['product__category__name'] or 'N/A',
            row['total_clicks'],
            row['detail_views'],
            row['total_events'],
            row['unique_kiosks']
        ])

    return response


# ==============================================================================
# APP RELEASES & REMOTE UPDATE MANAGEMENT
# ==============================================================================

def admin_releases(request):
    """
    App Release and Remote Kiosk Update Management Dashboard.
    Shows latest release overview, kiosk update progress telemetry,
    release history, and individual terminal controls (Check/Force Update).
    """
    if not request.user.is_authenticated:
        return redirect('signin')

    if request.method == "POST":
        action = request.POST.get('action')
        kiosk_id = request.POST.get('kiosk_id')
        release_id = request.POST.get('release_id')

        if action == "check_update_single" and kiosk_id:
            kiosk = get_object_or_404(KioskDevice, id=kiosk_id)
            kiosk.check_update_requested = True
            kiosk.save(update_fields=['check_update_requested'])
            messages.success(request, f"Check Update requested for '{kiosk.name}'. Command queued for next heartbeat.")
            return redirect('admin_releases')

        elif action == "force_update_single" and kiosk_id:
            kiosk = get_object_or_404(KioskDevice, id=kiosk_id)
            kiosk.force_update_requested = True
            kiosk.save(update_fields=['force_update_requested'])
            messages.success(request, f"Force Update requested for '{kiosk.name}'. Installation will begin on next heartbeat.")
            return redirect('admin_releases')

        elif action == "check_update_all":
            updated_count = KioskDevice.objects.filter(is_active=True).update(check_update_requested=True)
            messages.success(request, f"Triggered update checks across {updated_count} active kiosks.")
            return redirect('admin_releases')

        elif action == "force_update_all":
            updated_count = KioskDevice.objects.filter(is_active=True).update(force_update_requested=True)
            messages.warning(request, f"Triggered force update across {updated_count} active kiosks.")
            return redirect('admin_releases')

        elif action == "publish_release" and release_id:
            rel = get_object_or_404(AppRelease, id=release_id)
            rel.is_published = True
            if not rel.published_at:
                rel.published_at = timezone.now()
            rel.save(update_fields=['is_published', 'published_at'])
            dispatched = KioskDevice.objects.filter(is_active=True).update(force_update_requested=True)
            messages.success(request, f"Release v{rel.version_name} ({rel.version_code}) published successfully. Dispatched update signal to {dispatched} kiosks.")
            return redirect('admin_releases')

        elif action == "unpublish_release" and release_id:
            rel = get_object_or_404(AppRelease, id=release_id)
            rel.is_published = False
            rel.save(update_fields=['is_published'])
            messages.warning(request, f"Release v{rel.version_name} has been unpublished.")
            return redirect('admin_releases')

        elif action == "delete_release" and release_id:
            rel = get_object_or_404(AppRelease, id=release_id)
            rel_ver = f"v{rel.version_name} ({rel.version_code})"
            rel.delete()
            messages.success(request, f"Release {rel_ver} deleted successfully.")
            return redirect('admin_releases')

    releases = AppRelease.objects.all().order_by('-version_code')
    latest_release = releases.filter(is_published=True, is_active=True).first()

    kiosks = KioskDevice.objects.select_related('store').all().order_by('name')
    total_kiosks = kiosks.count()

    updated_count = 0
    pending_count = 0
    downloading_count = 0
    installing_count = 0
    failed_count = 0
    offline_count = 0

    latest_code = latest_release.version_code if latest_release else 0
    rel_ver = (latest_release.version_name or '').lower().lstrip('v').strip() if latest_release else ''

    now = timezone.now()
    kiosk_rows = []
    for k in kiosks:
        k_code = k.current_app_version_code or 1
        kiosk_ver = (k.app_version or '').lower().lstrip('v').strip()
        k_status = update_kiosk_status_and_alerts(k)
        is_online = (k_status == KioskDevice.Status.ONLINE)

        if latest_release:
            is_up_to_date = (k_code > latest_code) or (
                k_code == latest_code and (not kiosk_ver or kiosk_ver == rel_ver)
            )
        else:
            is_up_to_date = True

        if not is_online:
            offline_count += 1

        # Reconcile effective OTA update status
        effective_status = k.update_status
        if is_up_to_date:
            effective_status = KioskDevice.UpdateStatus.UP_TO_DATE
            if k.update_status != KioskDevice.UpdateStatus.UP_TO_DATE or k.force_update_requested:
                k.update_status = KioskDevice.UpdateStatus.UP_TO_DATE
                k.force_update_requested = False
                k.pending_update_release = None
                k.save(update_fields=['update_status', 'force_update_requested', 'pending_update_release'])
        elif effective_status in [KioskDevice.UpdateStatus.DOWNLOADING, KioskDevice.UpdateStatus.INSTALLING]:
            if not k.update_started_at or (now - k.update_started_at).total_seconds() > 900:
                effective_status = KioskDevice.UpdateStatus.FAILED
                k.update_status = KioskDevice.UpdateStatus.FAILED
                k.update_error = "Installation timed out or was interrupted"
                k.save(update_fields=['update_status', 'update_error'])
        elif effective_status == KioskDevice.UpdateStatus.UP_TO_DATE:
            effective_status = KioskDevice.UpdateStatus.UPDATE_AVAILABLE
            k.update_status = KioskDevice.UpdateStatus.UPDATE_AVAILABLE
            k.save(update_fields=['update_status'])

        if effective_status == KioskDevice.UpdateStatus.DOWNLOADING:
            downloading_count += 1
        elif effective_status == KioskDevice.UpdateStatus.INSTALLING:
            installing_count += 1
        elif effective_status == KioskDevice.UpdateStatus.FAILED:
            failed_count += 1
        elif is_up_to_date:
            updated_count += 1
        else:
            pending_count += 1

        disp_ver = k.app_version or f"1.0.{k_code}"
        if not disp_ver.startswith('v'):
            disp_ver = f"v{disp_ver}"

        kiosk_rows.append({
            'kiosk': k,
            'is_online': is_online,
            'current_version': disp_ver,
            'current_code': k_code,
            'latest_code': latest_code,
            'is_up_to_date': is_up_to_date,
            'update_status': effective_status,
            'last_seen': k.last_seen_at.strftime('%Y-%m-%d %H:%M') if k.last_seen_at else 'Never',
            'last_check': k.last_update_check.strftime('%Y-%m-%d %H:%M') if k.last_update_check else 'Never'
        })

    context = {
        'releases': releases,
        'latest_release': latest_release,
        'total_kiosks': total_kiosks,
        'updated_count': updated_count,
        'pending_count': pending_count,
        'downloading_count': downloading_count,
        'installing_count': installing_count,
        'failed_count': failed_count,
        'offline_count': offline_count,
        'kiosk_rows': kiosk_rows,
        'active_tab': 'releases',
        'page_title': 'App Releases & OTA Updates',
        'breadcrumbs': [
            {'name': 'Dashboard', 'url': '/admin_pannel/'},
            {'name': 'App Releases', 'url': ''}
        ]
    }
    return render(request, "admin/releases.html", context)


def admin_release_add(request):
    """
    Upload and configure a new Android APK application release.
    Validates APK structure, computes SHA-256 and byte size, and provisions rollout.
    """
    if not request.user.is_authenticated:
        return redirect('signin')

    kiosks = KioskDevice.objects.all().order_by('name')
    latest_rel = AppRelease.objects.order_by('-version_code').first()
    suggested_code = (latest_rel.version_code + 1) if latest_rel else 1

    if request.method == "POST":
        version_name = request.POST.get('version_name', '').strip()
        version_code_str = request.POST.get('version_code', '').strip()
        release_title = request.POST.get('release_title', '').strip()
        release_notes = request.POST.get('release_notes', '').strip()
        is_mandatory = request.POST.get('is_mandatory') == 'on'
        is_published = request.POST.get('is_published') == 'on'
        allow_rollback = request.POST.get('allow_rollback') == 'on'
        target_device_type = request.POST.get('target_device_type', AppRelease.DeviceType.ALL)
        staged_percentage_str = request.POST.get('staged_rollout_percentage', '100').strip()
        target_kiosk_ids = request.POST.getlist('target_kiosks')
        apk_url = request.POST.get('apk_url', '').strip()
        apk_file = request.FILES.get('apk_file')

        errors = []

        if not version_name:
            errors.append("Version Name is required (e.g. 1.0.5).")
        
        try:
            version_code = int(version_code_str)
            if version_code <= 0:
                errors.append("Version Code must be a positive integer.")
        except (ValueError, TypeError):
            errors.append("Valid integer Version Code is required (e.g. 105).")
            version_code = 0

        if not release_title:
            errors.append("Release Title is required.")

        try:
            staged_percentage = int(staged_percentage_str)
            if not (1 <= staged_percentage <= 100):
                errors.append("Staged rollout percentage must be between 1 and 100.")
        except ValueError:
            staged_percentage = 100

        # Validate unique version_code
        if AppRelease.objects.filter(version_code=version_code).exists():
            errors.append(f"A release with Version Code {version_code} already exists.")

        # Check monotonic increase
        highest_published = AppRelease.objects.filter(is_published=True).order_by('-version_code').first()
        if highest_published and is_published and version_code <= highest_published.version_code and not allow_rollback:
            errors.append(
                f"Version Code ({version_code}) must be higher than currently published release "
                f"v{highest_published.version_name} ({highest_published.version_code}). "
                f"To override for a rollback build, enable the 'Rollback / Emergency Downgrade' checkbox."
            )

        if not apk_file and not apk_url:
            errors.append("Please upload an APK file or provide a direct download APK URL.")

        sha256 = ""
        file_size = 0
        if apk_file:
            try:
                validate_apk_file(apk_file)
                sha256, file_size = compute_file_sha256_and_size(apk_file)
            except Exception as e:
                errors.append(f"APK validation failed: {str(e)}")

        if errors:
            for err in errors:
                messages.error(request, err)
            return render(request, "admin/release_add.html", {
                'kiosks': kiosks,
                'suggested_code': suggested_code,
                'target_kiosk_ids': target_kiosk_ids,
                'target_device_types': AppRelease.DeviceType.choices,
                'form_data': request.POST,
                'active_tab': 'releases',
                'page_title': 'Upload New App Release',
                'breadcrumbs': [
                    {'name': 'App Releases', 'url': '/admin_pannel/releases/'},
                    {'name': 'Upload Release', 'url': ''}
                ]
            })

        release = AppRelease(
            version_name=version_name,
            version_code=version_code,
            release_title=release_title,
            release_notes=release_notes,
            apk_file=apk_file,
            apk_url=apk_url,
            apk_file_size=file_size if apk_file else None,
            checksum_sha256=sha256,
            is_mandatory=is_mandatory,
            is_published=is_published,
            published_at=timezone.now() if is_published else None,
            target_device_type=target_device_type,
            staged_rollout_percentage=staged_percentage,
            created_by=request.user
        )
        release.save()

        if target_kiosk_ids:
            release.target_kiosks.set(target_kiosk_ids)

        if is_published:
            if target_kiosk_ids:
                KioskDevice.objects.filter(id__in=target_kiosk_ids, is_active=True).update(force_update_requested=True)
            else:
                KioskDevice.objects.filter(is_active=True).update(force_update_requested=True)

        messages.success(
            request, 
            f"Release v{release.version_name} ({release.version_code}) successfully created!"
            + (" Published and dispatched to kiosks." if is_published else " Saved as draft.")
        )
        return redirect('admin_releases')

    return render(request, "admin/release_add.html", {
        'kiosks': kiosks,
        'suggested_code': suggested_code,
        'target_device_types': AppRelease.DeviceType.choices,
        'active_tab': 'releases',
        'page_title': 'Upload New App Release',
        'breadcrumbs': [
            {'name': 'App Releases', 'url': '/admin_pannel/releases/'},
            {'name': 'Upload Release', 'url': ''}
        ]
    })


def admin_release_detail(request, release_id):
    """View details, checksums, targeting rules, and update history for a specific release."""
    if not request.user.is_authenticated:
        return redirect('signin')

    release = get_object_or_404(AppRelease.objects.prefetch_related('target_kiosks'), id=release_id)
    logs = KioskUpdateLog.objects.filter(release=release).select_related('kiosk').order_by('-created_at')[:50]

    return render(request, "admin/release_detail.html", {
        'release': release,
        'logs': logs,
        'active_tab': 'releases',
        'page_title': f"App Release: v{release.version_name} ({release.version_code})",
        'breadcrumbs': [
            {'name': 'App Releases', 'url': '/admin_pannel/releases/'},
            {'name': f"v{release.version_name}", 'url': ''}
        ]
    })




