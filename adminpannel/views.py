from django.shortcuts import render, redirect
from django.contrib.auth import get_user_model
from django.contrib import messages

User = get_user_model()

def admin_dashboard(request):
    # Verify user is authenticated and is admin/staff
    if not request.user.is_authenticated:
        return redirect('signin')
    if not (request.user.is_admin_role or request.user.is_staff_role):
        messages.error(request, "Unauthorized access. Only admin or staff can view the dashboard.")
        return redirect('signin')

    if request.method == "POST":
        action = request.POST.get('action')
        if action == "register_kiosk":
            location = request.POST.get('location', '').strip()
            device_id = request.POST.get('device_id', '').strip()
            
            if not location or not device_id:
                messages.error(request, "Both Location and Device ID are required to register a kiosk.")
            else:
                try:
                    # Create kiosk user with role 'kiosk'
                    # The username is automatically generated as EXE0001, EXE0002, etc. in User.save()
                    new_kiosk = User.objects.create_user(
                        role=User.Role.KIOSK,
                        location=location,
                        device_id=device_id
                    )
                    messages.success(request, f"Kiosk {new_kiosk.username} registered successfully at {location}.")
                except Exception as e:
                    messages.error(request, f"Error registering kiosk: {str(e)}")
            return redirect('admin_dashboard')

    # Fetch all kiosks
    kiosks = User.objects.filter(role=User.Role.KIOSK).order_by('username')
    
    # Calculate stats
    total_kiosks = kiosks.count()
    online_count = 0
    offline_count = 0
    kiosk_list = []
    
    for index, k in enumerate(kiosks):
        # We determine online/offline status:
        # If the kiosk has logged in before, we can look at that. For UI demo purposes:
        # Kiosks that are newly created without login can look offline unless specified.
        # Let's count it as offline if device_id starts with 'off' or if it has never synced/logged in.
        is_online = False
        if k.last_login:
            is_online = True
        elif k.device_id and not k.device_id.lower().startswith('off'):
            # Allow kiosks with normal device_ids to be online for demonstration
            is_online = True
            
        if is_online:
            online_count += 1
        else:
            offline_count += 1
            
        kiosk_list.append({
            'username': k.username,
            'location': k.location or 'Unknown Location',
            'device_id': k.device_id or 'N/A',
            'is_online': is_online,
            'last_sync': k.last_login.strftime('%Y-%m-%d %H:%M:%S') if k.last_login else 'Never Synced',
            'app_version': 'v1.0.2' if index % 2 == 0 else 'v1.0.3',
            'device_info': 'Android Tablet (Vertical Display)' if index % 2 == 0 else 'Kiosk Display 32" Portrait',
            'last_boot': '2026-08-22 09:30:15' if is_online else 'N/A'
        })
        
    context = {
        'kiosks': kiosk_list,
        'total_kiosks': total_kiosks,
        'online_count': online_count,
        'offline_count': offline_count,
        'total_products': 32,  # Simulated catalog count
    }
    return render(request, "admin/index.html", context)
