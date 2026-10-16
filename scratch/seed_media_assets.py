import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kiosk_backend.settings')
django.setup()

from products.models import Product
from content.models import MediaAsset

products = list(Product.objects.all())
print(f"Total products available: {len(products)}")

sample_assets = [
    # Images
    {"title": "Copper Bonded Rod 250 Microns - Product Showcase", "type": "IMAGE", "file": "media_assets/copper-bonded-earthing-rod.jpg"},
    {"title": "Multi-Spike Lightning Arrester - High Res Render", "type": "IMAGE", "file": "products/copper_rods_4k_ultra_hd.png"},
    {"title": "Chemical Earthing Compound Installation Guide", "type": "IMAGE", "file": "media_assets/copper-bonded-earthing-rod.jpg"},
    {"title": "Copper Bonded Earth Electrode - 4K Gallery View", "type": "IMAGE", "file": "products/copper_rods_4k_ultra_hd.png"},
    {"title": "Solid Copper Earth Plate - Technical Overview", "type": "IMAGE", "file": "media_assets/copper-bonded-earthing-rod.jpg"},
    {"title": "Cast Iron Earth Pit Cover - Detailed View", "type": "IMAGE", "file": "products/copper_rods_4k_ultra_hd.png"},
    {"title": "Exothermic Welding Mold Kit - Precision Diagram", "type": "IMAGE", "file": "media_assets/copper-bonded-earthing-rod.jpg"},
    {"title": "Pure Copper Tape Conductor - Coil Inspection", "type": "IMAGE", "file": "products/copper_rods_4k_ultra_hd.png"},

    # Brochures & PDFs
    {"title": "Excel Earthing Complete Product Catalog 2026", "type": "PDF_BROCHURE", "file": "media_assets/Please_share_the_following.pdf"},
    {"title": "UL Listed Copper Bonded Rods Technical Brochure", "type": "PDF_BROCHURE", "file": "media_assets/Please_share_the_following.pdf"},
    {"title": "Lightning Protection & Early Streamer Emission Manual", "type": "PDF_BROCHURE", "file": "media_assets/Please_share_the_following.pdf"},
    {"title": "Chemical Compound Soil Conductivity Test Report", "type": "PDF_BROCHURE", "file": "media_assets/Please_share_the_following.pdf"},
    {"title": "Earthing Standards Compliance Guide (IEEE 80 / IS 3043)", "type": "PDF_BROCHURE", "file": "media_assets/Please_share_the_following.pdf"},

    # 3D Assets
    {"title": "Interactive 3D Copper Bonded Earth Rod", "type": "THREE_D", "file": "media_assets/copper-bonded-earth-rod_JPxKz56.glb"},
    {"title": "Interactive 3D Multi-Spike Lightning Arrester", "type": "THREE_D", "file": "media_assets/copper-bonded-earth-rod_JPxKz56.glb"},
    {"title": "Interactive 3D Earth Pit Inspection Chamber", "type": "THREE_D", "file": "media_assets/copper-bonded-earth-rod_JPxKz56.glb"},
    {"title": "Interactive 3D Exothermic Graphite Mold", "type": "THREE_D", "file": "media_assets/copper-bonded-earth-rod_JPxKz56.glb"},
    {"title": "Interactive 3D Copper Clad Electrode Assembly", "type": "THREE_D", "file": "media_assets/copper-bonded-earth-rod_JPxKz56.glb"},

    # Tech Sheets
    {"title": "Material Specification Sheet - Copper Bonding Thickness", "type": "TECH_SHEET", "file": "media_assets/Please_share_the_following.pdf"},
    {"title": "Soil Resistivity Test Matrix & Chemical Dosage Table", "type": "TECH_SHEET", "file": "media_assets/Please_share_the_following.pdf"},
    {"title": "Tensile Strength & Bending Verification Certificate", "type": "TECH_SHEET", "file": "media_assets/Please_share_the_following.pdf"},

    # Video
    {"title": "Excel Corporate Manufacturing & Quality Testing Tour", "type": "VIDEO", "file": "", "external_url": "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4"},
    {"title": "Exothermic Welding Live Demonstration at Site", "type": "VIDEO", "file": "", "external_url": "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ElephantsDream.mp4"},
]

created_count = 0
for i, item in enumerate(sample_assets):
    prod = products[i % len(products)] if products else None
    existing = MediaAsset.objects.filter(title=item["title"]).first()
    if not existing:
        MediaAsset.objects.create(
            title=item["title"],
            asset_type=item["type"],
            file=item.get("file", ""),
            external_url=item.get("external_url", ""),
            product=prod,
            description=f"Official technical asset and documentation for {prod.name if prod else 'Excel Earthing solutions'}.",
            file_size_mb=1.25,
            is_active=True
        )
        created_count += 1

print(f"Created {created_count} new media assets. Total in DB: {MediaAsset.objects.count()}")
