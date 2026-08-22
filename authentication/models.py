from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
import re

class CustomUserManager(BaseUserManager):
    def create_user(self, username=None, email=None, password=None, **extra_fields):
        # We normalize email if provided, but it is not mandatory
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
        extra_fields.setdefault('role', 'admin')  # Set default role to admin for superuser

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
        help_text="Unique login ID. Leave blank to auto-generate based on role."
    )
    
    email = models.EmailField(blank=True, null=True)

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = []

    class Role(models.TextChoices):
        KIOSK = 'kiosk', 'Kiosk'
        ADMIN = 'admin', 'Admin'
        STAFF = 'staff', 'Staff'

    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.KIOSK,
        help_text="Designated role for this user"
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
        help_text="Device ID of the user"
    )

    @property
    def is_kiosk(self):
        return self.role == self.Role.KIOSK

    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN

    @property
    def is_staff_role(self):
        return self.role == self.Role.STAFF

    def save(self, *args, **kwargs):
        if not self.username:
            prefix = ""
            digits = 4
            if self.role == self.Role.STAFF:
                prefix = "STF"
                digits = 4
            elif self.role == self.Role.ADMIN:
                prefix = "ADMIN"
                digits = 2
            elif self.role == self.Role.KIOSK:
                prefix = "EXE"
                digits = 4
            
            # Find the latest user with this prefix
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
