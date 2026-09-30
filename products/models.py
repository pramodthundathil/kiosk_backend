import uuid
from django.db import models
from django.db.models import Q

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
        return Product.objects.filter(
            Q(category=self) | Q(sub_category__category=self),
            is_active=True,
            parent__isnull=True
        ).distinct().count()


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
    sku = models.CharField(max_length=100, unique=True, db_index=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='products', help_text="Main Category")
    sub_category = models.ForeignKey(SubCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='products', help_text="Sub-Category / Product Category")
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='child_variants', help_text="Parent main product if this is a variant product")
    description = models.TextField(blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    stock = models.IntegerField(default=100)
    specifications = models.JSONField(default=dict, blank=True)
    features = models.JSONField(default=list, blank=True, help_text="List of feature points with optional sub-points")
    certifications = models.JSONField(default=list, blank=True, help_text="List of certifications with test sub-points")
    in_house_tests = models.JSONField(default=list, blank=True, help_text="List of in-house tests with sub-points")
    applicable_areas = models.JSONField(default=list, blank=True, help_text="List of applicable installation and industry areas")
    image = models.ImageField(upload_to='products/', blank=True, null=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.sku})"

    def generate_sku(self):
        import re
        if self.parent and self.parent.sku:
            base = f"{self.parent.sku}-V"
            idx = 1
            candidate = f"{base}{idx}"
            while Product.objects.filter(sku=candidate).exclude(id=self.id).exists():
                idx += 1
                candidate = f"{base}{idx}"
            return candidate

        prefix = "EXE"
        if self.sub_category and self.sub_category.code:
            prefix = self.sub_category.code.upper().replace('_', '-')
        elif self.category and self.category.code:
            prefix = self.category.code.upper().replace('_', '-')
        
        words = [re.sub(r'[^A-Za-z0-9]', '', w).upper() for w in (self.name or "ITEM").split() if w]
        short_name = '-'.join(w[:4] for w in words[:3]) if words else "ITEM"
        
        candidate_base = f"{prefix}-{short_name}"
        candidate = candidate_base
        counter = 1
        while Product.objects.filter(sku=candidate).exclude(id=self.id).exists():
            candidate = f"{candidate_base}-{counter}"
            counter += 1
        return candidate

    def save(self, *args, **kwargs):
        # Auto-sync parent category from sub_category if category is not explicitly set
        if self.sub_category and not self.category:
            self.category = self.sub_category.category
        if not self.sku or not str(self.sku).strip():
            self.sku = self.generate_sku()
        else:
            self.sku = self.sku.strip()
        super().save(*args, **kwargs)

    @property
    def is_variant(self):
        return self.parent_id is not None

    @property
    def main_product(self):
        return self.parent if self.parent else self

    @property
    def family_variants(self):
        """Returns all products in the same variant family (including parent and children)."""
        main = self.main_product
        return Product.objects.filter(
            Q(id=main.id) | Q(parent=main),
            is_active=True
        ).order_by('name')

    @property
    def direct_variants(self):
        """Returns child products attached to this product as variants."""
        return self.child_variants.filter(is_active=True).order_by('name')

    @property
    def sub_products(self):
        """Backwards compatibility alias for direct variants."""
        return self.direct_variants

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



