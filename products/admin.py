from django.contrib import admin
from .models import Category, SubCategory, Product, ProductShare

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'display_order', 'is_active', 'created_at')
    search_fields = ('name', 'code')
    list_filter = ('is_active',)

@admin.register(SubCategory)
class SubCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'category', 'display_order', 'is_active', 'created_at')
    search_fields = ('name', 'code', 'category__name')
    list_filter = ('category', 'is_active')

class ProductVariantInline(admin.TabularInline):
    model = Product
    fk_name = 'parent'
    extra = 0
    fields = ('name', 'sku', 'price', 'stock', 'is_active')
    verbose_name = 'Child Variant Product'
    verbose_name_plural = 'Child Variant Products'

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'sku', 'parent', 'category', 'sub_category', 'price', 'stock', 'is_active')
    search_fields = ('name', 'sku', 'category__name', 'sub_category__name')
    list_filter = ('category', 'sub_category', 'is_active', ('parent', admin.EmptyFieldListFilter))
    inlines = [ProductVariantInline]

@admin.register(ProductShare)
class ProductShareAdmin(admin.ModelAdmin):
    list_display = ('staff_user', 'customer_name', 'customer_phone', 'product', 'shared_via', 'created_at')
    search_fields = ('customer_name', 'customer_phone', 'staff_user__username', 'product__name')
    list_filter = ('shared_via', 'created_at')


