from rest_framework import serializers
from .models import MediaAsset
from products.models import Product, Category, SubCategory

class MediaLibraryAssetSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    asset_type_display = serializers.CharField(source='get_asset_type_display', read_only=True)
    product_id = serializers.UUIDField(source='product.id', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)
    category_id = serializers.SerializerMethodField()
    category_name = serializers.SerializerMethodField()
    category_code = serializers.SerializerMethodField()
    sub_category_name = serializers.SerializerMethodField()

    class Meta:
        model = MediaAsset
        fields = [
            'id',
            'title',
            'asset_type',
            'asset_type_display',
            'file',
            'file_url',
            'thumbnail_url',
            'external_url',
            'file_size_mb',
            'description',
            'product_id',
            'product_name',
            'product_sku',
            'category_id',
            'category_name',
            'category_code',
            'sub_category_name',
            'created_at',
            'updated_at',
        ]

    def _get_absolute_url(self, file_field):
        if not file_field:
            return None
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(file_field.url)
        return file_field.url

    def get_file_url(self, obj):
        if obj.file:
            return self._get_absolute_url(obj.file)
        return obj.external_url or None

    def get_thumbnail_url(self, obj):
        # If this is an image, the file itself is the thumbnail
        if obj.asset_type == MediaAsset.AssetType.IMAGE and obj.file:
            return self._get_absolute_url(obj.file)
        
        # If associated with a product with an image, use the product's image as the poster/thumbnail
        if obj.product and obj.product.image:
            return self._get_absolute_url(obj.product.image)

        # Fallback to file_url if available
        if obj.file:
            return self._get_absolute_url(obj.file)
        return obj.external_url or None

    def get_category_id(self, obj):
        if obj.product:
            if obj.product.category:
                return str(obj.product.category.id)
            if obj.product.sub_category and obj.product.sub_category.category:
                return str(obj.product.sub_category.category.id)
        return None

    def get_category_name(self, obj):
        if obj.product:
            if obj.product.category:
                return obj.product.category.name
            if obj.product.sub_category and obj.product.sub_category.category:
                return obj.product.sub_category.category.name
        return "General"

    def get_category_code(self, obj):
        if obj.product:
            if obj.product.category:
                return obj.product.category.code
            if obj.product.sub_category and obj.product.sub_category.category:
                return obj.product.sub_category.category.code
        return "GENERAL"

    def get_sub_category_name(self, obj):
        if obj.product and obj.product.sub_category:
            return obj.product.sub_category.name
        return None
