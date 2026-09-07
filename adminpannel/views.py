from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.utils import timezone
from stores.models import Store
from kiosks.models import KioskDevice, KioskProfile
from kiosks.services import register_kiosk_device, update_kiosk_credential
from monitoring.models import Alert, KioskEvent
from monitoring.services import update_kiosk_status_and_alerts
from products.models import Product, Category
from content.models import MediaAsset

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
            try:
                kiosk = KioskDevice.objects.get(id=kiosk_id)
                current_ver = int(kiosk.desired_content_version) if kiosk.desired_content_version.isdigit() else 1
                kiosk.desired_content_version = str(current_ver + 1)
                kiosk.save(update_fields=['desired_content_version'])
                KioskEvent.objects.create(
                    kiosk=kiosk,
                    event_type=KioskEvent.EventType.SYNC_STARTED,
                    severity=KioskEvent.Severity.INFO,
                    message=f"Force sync triggered by admin ({request.user.username}). Desired version set to {kiosk.desired_content_version}."
                )
                messages.success(request, f"Force Sync requested for Kiosk [{kiosk.device_id}].")
            except KioskDevice.DoesNotExist:
                messages.error(request, "Kiosk device not found.")
            return redirect('admin_kiosks')

    kiosks = KioskDevice.objects.select_related('store', 'profile').all().order_by('-created_at')
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
    """Single detailed view of a specific kiosk terminal with hardware specs, store, profile, telemetry, and edit links."""
    if not request.user.is_authenticated:
        return redirect('signin')

    kiosk = get_object_or_404(KioskDevice.objects.select_related('store', 'profile'), id=kiosk_id)
    status = update_kiosk_status_and_alerts(kiosk)
    recent_events = KioskEvent.objects.filter(kiosk=kiosk).order_by('-created_at')[:15]
    open_alerts = Alert.objects.filter(kiosk=kiosk, resolved_at__isnull=True).order_by('-opened_at')

    context = {
        'kiosk': kiosk,
        'status': status,
        'is_online': (status == KioskDevice.Status.ONLINE),
        'recent_events': recent_events,
        'open_alerts': open_alerts,
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
            elif Product.objects.filter(sku=sku).exists():
                messages.error(request, f"Product SKU '{sku}' already exists.")
            else:
                category = Category.objects.filter(id=category_id).first() if category_id else None
                Product.objects.create(
                    name=name,
                    sku=sku,
                    category=category,
                    price=price or 0.00,
                    stock=stock or 100,
                    description=description,
                    image=image
                )
                messages.success(request, f"Product '{name}' added to catalog successfully.")
            return redirect('admin_products')

        elif action == "update_product":
            product_id = request.POST.get('product_id')
            try:
                product = Product.objects.get(id=product_id)
                product.name = request.POST.get('name', product.name).strip()
                product.price = request.POST.get('price', product.price)
                product.stock = request.POST.get('stock', product.stock)
                product.description = request.POST.get('description', product.description).strip()
                cat_id = request.POST.get('category_id', '').strip()
                product.category = Category.objects.filter(id=cat_id).first() if cat_id else product.category
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

    products = Product.objects.select_related('category').filter(is_active=True).order_by('-created_at')
    categories = Category.objects.filter(is_active=True).order_by('name')

    context = {
        'products': products,
        'categories': categories,
        'total_products': products.count(),
        'active_tab': 'products',
    }
    return render(request, "admin/products.html", context)


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
    kiosk_list = []
    for k in kiosks:
        status = update_kiosk_status_and_alerts(k)
        kiosk_list.append({
            'id': str(k.id),
            'username': k.name,
            'device_id': k.device_id,
            'location': k.store.name if k.store else 'Unspecified Location',
            'status': status,
            'is_online': (status == KioskDevice.Status.ONLINE),
            'last_sync': k.last_sync_at.strftime('%Y-%m-%d %H:%M:%S') if k.last_sync_at else 'Never Synced',
            'app_version': k.app_version or 'v1.0.0',
            'device_info': f"{k.manufacturer or ''} {k.device_model or ''}".strip() or 'Android Display',
            'last_boot': k.last_seen_at.strftime('%Y-%m-%d %H:%M:%S') if k.last_seen_at else 'N/A',
        })

    open_alerts = Alert.objects.filter(resolved_at__isnull=True).select_related('kiosk')[:20]

    context = {
        'kiosks': kiosk_list,
        'open_alerts': open_alerts,
        'active_tab': 'monitoring',
    }
    return render(request, "admin/monitoring.html", context)


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
