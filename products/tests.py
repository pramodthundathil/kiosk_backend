from django.test import TestCase, Client
from django.urls import reverse
from products.models import Product, Category, SubCategory
from content.models import MediaAsset
import uuid


class PublicProductViewsTestCase(TestCase):
    def setUp(self):
        self.client = Client()

        # Create Category and SubCategory
        self.category = Category.objects.create(
            name="Chemical Earthing",
            code="CHEM-EARTH",
            description="Advanced chemical earthing electrodes",
            display_order=1
        )
        self.sub_category = SubCategory.objects.create(
            category=self.category,
            name="Copper Electrodes",
            code="COPPER-ELEC",
            description="Pure copper bonded chemical earthing electrodes",
            display_order=1
        )

        # Create Main Product
        self.main_product = Product.objects.create(
            name="Copper Bonded Chemical Earth Electrode",
            sku="EXE-CBE-3M",
            category=self.category,
            sub_category=self.sub_category,
            description="Ultra low-resistance maintenance free earthing electrode with 250 micron copper bonding.",
            price=3500.00,
            stock=50,
            specifications={
                "Length": "3000 mm (3 Meters)",
                "Outer Diameter": "50 mm",
                "Copper Coating Thickness": "250 Microns",
                "Fault Current Rating": "40 kA for 1 sec",
                "Terminal Size": "50x6 mm Copper Flat"
            },
            features=[
                {"title": "CPRI Tested", "description": "Successfully withstands 40kA short-circuit fault current."},
                {"title": "Corrosion Shield", "description": "Molecularly bonded copper resists acidic and saline soil."},
                "Maintenance free throughout entire operational lifespan"
            ],
            certifications=[
                {"title": "CPRI Certified", "description": "Short circuit test as per IEC 62561-2"},
                "ISO 9001:2015 Quality Standard"
            ],
            in_house_tests=[
                {"title": "Adhesion Test", "description": "Copper coating adherence test per UL 467"},
                "Bending & Tensile Strength Evaluation"
            ],
            applicable_areas=[
                "High Voltage Power Substations",
                "Solar Power Plants & Wind Farms",
                "Data Centers & IT Infrastructure",
                "Lightning Protection Down Conductors"
            ],
            is_active=True
        )

        # Create Child Variant
        self.variant_product = Product.objects.create(
            name="Copper Bonded Earth Electrode (2 Meter Variant)",
            sku="EXE-CBE-2M",
            parent=self.main_product,
            category=self.category,
            sub_category=self.sub_category,
            description="2 meter version of the chemical earth electrode.",
            price=2800.00,
            stock=30,
            specifications={
                "Length": "2000 mm (2 Meters)",
                "Outer Diameter": "50 mm"
            },
            is_active=True
        )

        # Create Media Asset
        self.doc_asset = MediaAsset.objects.create(
            title="Copper Earth Electrode Technical Datasheet",
            asset_type=MediaAsset.AssetType.TECH_SHEET,
            external_url="https://excelearting.com/docs/copper-electrode-datasheet.pdf",
            file_size_mb=1.8,
            product=self.main_product
        )

    def test_public_product_detail_by_uuid(self):
        """Test retrieving product detail page by product UUID."""
        url = reverse('public_product_detail', kwargs={'identifier': self.main_product.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.main_product.name)
        self.assertContains(response, self.main_product.sku)
        self.assertContains(response, "₹3500")
        self.assertContains(response, "In Stock & Ready for Dispatch")
        self.assertContains(response, "Copper Coating Thickness")
        self.assertContains(response, "250 Microns")
        self.assertContains(response, "CPRI Tested")
        self.assertContains(response, "High Voltage Power Substations")
        self.assertContains(response, "Inquire via WhatsApp")

    def test_public_product_detail_by_sku(self):
        """Test retrieving product detail page by product SKU code."""
        url = reverse('public_product_detail_by_code', kwargs={'identifier': self.main_product.sku})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.main_product.name)

    def test_public_product_detail_variant_selector(self):
        """Test that the variant selector is present and lists family models."""
        url = reverse('public_product_detail', kwargs={'identifier': self.main_product.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['has_variants'])
        self.assertEqual(len(response.context['variants_list']), 2)
        self.assertContains(response, "EXE-CBE-2M")

    def test_public_product_detail_not_found(self):
        """Test 404 response for invalid product identifier."""
        fake_uuid = uuid.uuid4()
        url = reverse('public_product_detail', kwargs={'identifier': fake_uuid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_public_product_list(self):
        """Test public catalog listing page."""
        url = reverse('public_product_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.main_product.name)
        self.assertContains(response, "Chemical Earthing")

    def test_public_product_list_search(self):
        """Test search filtering in public catalog."""
        url = reverse('public_product_list') + "?q=Copper"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.main_product.name)

        url_no_match = reverse('public_product_list') + "?q=NonExistentDevice12345"
        response_no_match = self.client.get(url_no_match)
        self.assertEqual(response_no_match.status_code, 200)
        self.assertContains(response_no_match, "No products found")

    def test_public_product_list_category_filter(self):
        """Test category filtering in public catalog."""
        url = reverse('public_product_list') + f"?category={self.category.code}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.main_product.name)
