from django.contrib import admin
from .models import Category, SubCategory, Product

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

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'sku', 'category', 'sub_category', 'price', 'stock', 'is_active')
    search_fields = ('name', 'sku', 'category__name', 'sub_category__name')
    list_filter = ('category', 'sub_category', 'is_active')
