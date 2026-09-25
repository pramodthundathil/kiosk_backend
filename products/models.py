import uuid
from django.db import models

class Category(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=60, unique=True, db_index=True)
    description = models.TextField(blank=True, null=True)
    image = models.ImageField(upload_to='categories/', blank=True, null=True, help_text="Category representative image (white background preferred)")
    display_order = models.PositiveIntegerField(default=0, help_text="Sort order for catalog presentation")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['display_order', 'name']

    def __str__(self):
        return self.name

    @property
    def active_subcategories(self):
        return self.subcategories.filter(is_active=True).order_by('display_order', 'name')

    @property
    def all_products_count(self):
        return self.products.filter(is_active=True).count()


class SubCategory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='subcategories', help_text="Parent main category")
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=60, db_index=True)
    description = models.TextField(blank=True, null=True)
    image = models.ImageField(upload_to='subcategories/', blank=True, null=True, help_text="Sub-category representative image")
    display_order = models.PositiveIntegerField(default=0, help_text="Sort order within parent category")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Product Category / Sub-Category"
        verbose_name_plural = "Product Categories / Sub-Categories"
        ordering = ['display_order', 'name']
        unique_together = [('category', 'code')]

    def __str__(self):
        return f"{self.category.name} → {self.name}"

    @property
    def active_products(self):
        return self.products.filter(is_active=True).order_by('-created_at')

    @property
    def products_count(self):
        return self.products.filter(is_active=True).count()


class Product(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=100, unique=True, db_index=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='products', help_text="Main Category")
    sub_category = models.ForeignKey(SubCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='products', help_text="Sub-Category / Product Category")
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='sub_products', help_text="Optional parent product if this is a sub-product/variant")
    description = models.TextField(blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    stock = models.IntegerField(default=100)
    specifications = models.JSONField(default=dict, blank=True)
    image = models.ImageField(upload_to='products/', blank=True, null=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.sku})"

    def save(self, *args, **kwargs):
        # Auto-sync parent category from sub_category if category is not explicitly set
        if self.sub_category and not self.category:
            self.category = self.sub_category.category
        super().save(*args, **kwargs)

    @property
    def images(self):
        return self.media_assets.filter(asset_type='IMAGE', is_active=True)

    @property
    def videos(self):
        return self.media_assets.filter(asset_type='VIDEO', is_active=True)

    @property
    def brochures(self):
        return self.media_assets.filter(asset_type='PDF_BROCHURE', is_active=True)

    @property
    def tech_sheets(self):
        return self.media_assets.filter(asset_type='TECH_SHEET', is_active=True)

    @property
    def three_d_assets(self):
        return self.media_assets.filter(asset_type='THREE_D', is_active=True)

