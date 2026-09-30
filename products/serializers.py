from rest_framework import serializers
from .models import Product, Category, SubCategory, ProductShare

from content.models import MediaAsset


class SubCategorySimpleSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    category_id = serializers.UUIDField(source='category.id', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    category_code = serializers.CharField(source='category.code', read_only=True)
    products_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = SubCategory
        fields = [
            'id', 'name', 'code', 'description', 'image', 'image_url', 
            'display_order', 'is_active', 'created_at',
            'category_id', 'category_name', 'category_code', 'products_count'
        ]

    def get_image_url(self, obj):
        if obj.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None


class CategorySerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    subcategories = serializers.SerializerMethodField()
    subcategories_count = serializers.SerializerMethodField()
    products_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            'id', 'name', 'code', 'description', 'image', 'image_url', 
            'display_order', 'is_active', 'created_at',
            'subcategories', 'subcategories_count', 'products_count'
        ]

    def get_image_url(self, obj):
        if obj.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None

    def get_subcategories(self, obj):
        active_subs = obj.subcategories.filter(is_active=True).order_by('display_order', 'name')
        return SubCategorySimpleSerializer(active_subs, many=True, context=self.context).data

    def get_subcategories_count(self, obj):
        return obj.subcategories.filter(is_active=True).count()

    def get_products_count(self, obj):
        from django.db.models import Q
        return Product.objects.filter(
            Q(category=obj) | Q(sub_category__category=obj),
            is_active=True,
            parent__isnull=True
        ).distinct().count()



class SubCategoryDetailSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    category = CategorySerializer(read_only=True)
    category_id = serializers.UUIDField(write_only=True)
    products_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = SubCategory
        fields = [
            'id', 'category', 'category_id', 'name', 'code', 
            'description', 'image_url', 'display_order', 'products_count'
        ]

    def get_image_url(self, obj):
        if obj.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None


class ProductMediaAssetSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()
    asset_type_display = serializers.CharField(source='get_asset_type_display', read_only=True)

    class Meta:
        model = MediaAsset
        fields = [
            'id', 'title', 'asset_type', 'asset_type_display', 
            'file', 'file_url', 'external_url', 'file_size_mb', 
            'description', 'created_at'
        ]

    def get_file_url(self, obj):
        request = self.context.get('request')
        if obj.file:
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return obj.external_url or None


class ProductVariantSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    category_id = serializers.UUIDField(source='category.id', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    sub_category_id = serializers.UUIDField(source='sub_category.id', read_only=True)
    sub_category_name = serializers.CharField(source='sub_category.name', read_only=True)
    media_assets = ProductMediaAssetSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'parent_id', 'name', 'sku', 'price', 'stock',
            'image', 'image_url', 'description', 'specifications', 'features',
            'certifications', 'in_house_tests', 'applicable_areas',
            'category_id', 'category_name', 'sub_category_id', 'sub_category_name',
            'media_assets', 'is_active', 'created_at', 'updated_at'
        ]

    def get_image_url(self, obj):
        if obj.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None


class SubProductSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ['id', 'name', 'sku', 'price', 'stock', 'image_url', 'description']

    def get_image_url(self, obj):
        if obj.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None


class ProductSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    category_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)
    sub_category = SubCategorySimpleSerializer(read_only=True)
    sub_category_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)
    parent_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)
    variants = ProductVariantSerializer(source='direct_variants', many=True, read_only=True)
    sub_products = SubProductSerializer(source='direct_variants', many=True, read_only=True)
    image_url = serializers.SerializerMethodField()
    media_assets = ProductMediaAssetSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'sku', 'category', 'category_id', 
            'sub_category', 'sub_category_id', 'parent_id', 'variants', 'sub_products',
            'description', 'price', 'stock', 'specifications', 
            'features', 'certifications', 'in_house_tests', 'applicable_areas',
            'image', 'image_url', 'media_assets', 'is_active', 
            'created_at', 'updated_at'
        ]

    def get_image_url(self, obj):
        if obj.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None


class ProductShareSerializer(serializers.ModelSerializer):
    staff_username = serializers.SerializerMethodField()
    product_name = serializers.CharField(source='product.name', read_only=True, default='')
    product_sku = serializers.CharField(source='product.sku', read_only=True, default='')
    variant_name = serializers.CharField(source='variant.name', read_only=True, default='')
    product_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)
    variant_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = ProductShare
        fields = [
            'id', 'staff_user', 'staff_username', 'customer_name', 'customer_phone',
            'product', 'product_id', 'product_name', 'product_sku',
            'variant', 'variant_id', 'variant_name',
            'shared_via', 'options', 'created_at'
        ]
        read_only_fields = ['id', 'staff_user', 'created_at']

    def get_staff_username(self, obj):
        return obj.staff_user.username if obj.staff_user else 'Staff'

    def create(self, validated_data):
        product_id = validated_data.pop('product_id', None)
        variant_id = validated_data.pop('variant_id', None)

        if product_id:
            try:
                validated_data['product'] = Product.objects.get(id=product_id)
            except Product.DoesNotExist:
                pass

        if variant_id:
            try:
                validated_data['variant'] = Product.objects.get(id=variant_id)
            except Product.DoesNotExist:
                pass

        return super().create(validated_data)



