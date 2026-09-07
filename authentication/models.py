from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
import re

class CustomUserManager(BaseUserManager):
    def create_user(self, username=None, email=None, password=None, **extra_fields):
        email = self.normalize_email(email) if email else email
        user = self.model(username=username, email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('role', 'super_admin')

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(username=username, email=email, password=password, **extra_fields)

class User(AbstractUser):
    username = models.CharField(
        max_length=150,
        unique=True,
        blank=True,
        help_text="Unique login ID. Auto-generated if left blank."
    )
    
    email = models.EmailField(blank=True, null=True)

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = []

    class Role(models.TextChoices):
        SUPER_ADMIN = 'super_admin', 'Super Admin'
        ADMIN = 'admin', 'Admin'
        CONTENT_MANAGER = 'content_manager', 'Content Manager'
        STORE_MANAGER = 'store_manager', 'Store Manager'
        MONITORING_MANAGER = 'monitoring_manager', 'Monitoring Manager'
        # Legacy values retained for database compatibility:
        STAFF = 'staff', 'Staff'
        KIOSK = 'kiosk', 'Kiosk (Legacy)'

    role = models.CharField(
        max_length=30,
        choices=Role.choices,
        default=Role.ADMIN,
        help_text="CMS user role"
    )

    assigned_stores = models.ManyToManyField(
        'stores.Store',
        blank=True,
        related_name='assigned_managers',
        help_text="Stores accessible by this user if role is Store Manager"
    )

    location = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Location of the user"
    )

    device_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Legacy device ID if applicable"
    )

    @property
    def is_kiosk(self):
        """Kiosks are KioskDevice models, not User objects."""
        return False

    @property
    def is_cms_user(self):
        return True

    @property
    def is_super_admin(self):
        return self.role == self.Role.SUPER_ADMIN or self.is_superuser


    @property
    def is_admin_role(self):
        return self.role in [self.Role.SUPER_ADMIN, self.Role.ADMIN] or self.is_superuser

    @property
    def is_content_manager(self):
        return self.role in [self.Role.SUPER_ADMIN, self.Role.ADMIN, self.Role.CONTENT_MANAGER] or self.is_superuser

    @property
    def is_store_manager(self):
        return self.role in [self.Role.SUPER_ADMIN, self.Role.ADMIN, self.Role.STORE_MANAGER] or self.is_superuser

    @property
    def is_monitoring_manager(self):
        return self.role in [self.Role.SUPER_ADMIN, self.Role.ADMIN, self.Role.MONITORING_MANAGER] or self.is_superuser

    def save(self, *args, **kwargs):
        if not self.username:
            prefix = "USR"
            digits = 4
            if self.role == self.Role.SUPER_ADMIN:
                prefix = "SADM"
            elif self.role == self.Role.ADMIN:
                prefix = "ADM"
            elif self.role == self.Role.CONTENT_MANAGER:
                prefix = "CNT"
            elif self.role == self.Role.STORE_MANAGER:
                prefix = "STR"
            elif self.role == self.Role.MONITORING_MANAGER:
                prefix = "MON"
            
            last_user = User.objects.filter(username__startswith=prefix).order_by('-username').first()
            if last_user:
                match = re.search(rf'^{prefix}(\d+)$', last_user.username)
                if match:
                    next_num = int(match.group(1)) + 1
                else:
                    next_num = 1
            else:
                next_num = 1
            
            self.username = f"{prefix}{next_num:0{digits}d}"
            
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

    objects = CustomUserManager()
