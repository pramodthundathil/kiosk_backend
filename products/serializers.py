from rest_framework import serializers
from .models import Product, Category, SubCategory
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
            'id', 'name', 'code', 'description', 'image_url', 
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
            'id', 'name', 'code', 'description', 'image_url', 
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
        return obj.products.filter(is_active=True).count()


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
    sub_products = SubProductSerializer(many=True, read_only=True)
    image_url = serializers.SerializerMethodField()
    media_assets = ProductMediaAssetSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'sku', 'category', 'category_id', 
            'sub_category', 'sub_category_id', 'parent_id', 'sub_products',
            'description', 'price', 'stock', 'specifications', 
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

