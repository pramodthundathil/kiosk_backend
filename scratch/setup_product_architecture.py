import os
import django
import uuid

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kiosk_backend.settings')
django.setup()

from products.models import Category, SubCategory, Product
from content.models import MediaAsset

print("--- Setting up Revised Product Architecture ---")

# 1. Main Categories
cat_earthing, _ = Category.objects.update_or_create(
    code='ELECTRICAL_EARTHING',
    defaults={
        'name': 'Electrical Earthing',
        'description': 'Engineered earthing systems, compounds, and electrodes meeting global standards.',
        'display_order': 1,
        'is_active': True,
    }
)

cat_lightning, _ = Category.objects.update_or_create(
    code='LIGHTNING_PROTECTION',
    defaults={
        'name': 'Lightning Protection',
        'description': 'Structural lightning protection, vertical air terminals, and down conductors.',
        'display_order': 2,
        'is_active': True,
    }
)

cat_spd, _ = Category.objects.update_or_create(
    code='SPD',
    defaults={
        'name': 'Surge Protection Devices',
        'description': 'Advanced transient voltage surge suppression for industrial panels and power grids.',
        'display_order': 3,
        'is_active': True,
    }
)

# 2. Sub-Categories under Electrical Earthing
sub_compounds, _ = SubCategory.objects.update_or_create(
    category=cat_earthing,
    code='EARTH_COMPOUNDS',
    defaults={
        'name': 'Earth Compounds',
        'description': 'High conductivity backfill compounds & concrete additives.',
        'display_order': 1,
        'is_active': True,
    }
)

sub_electrodes, _ = SubCategory.objects.update_or_create(
    category=cat_earthing,
    code='EARTH_ELECTRODES',
    defaults={
        'name': 'Earth Electrodes',
        'description': 'Copper bonded, pure copper and pipe-in-pipe earthing electrodes.',
        'display_order': 2,
        'is_active': True,
    }
)

sub_pit_covers, _ = SubCategory.objects.update_or_create(
    category=cat_earthing,
    code='PIT_COVERS',
    defaults={
        'name': 'Earth Pit Covers',
        'description': 'Heavy-duty inspection pits and polymer covers.',
        'display_order': 3,
        'is_active': True,
    }
)

# 3. Sub-Categories under Lightning Protection
sub_air_rods, _ = SubCategory.objects.update_or_create(
    category=cat_lightning,
    code='VERTICAL_AIR_RODS',
    defaults={
        'name': 'Vertical Air Termination Rods',
        'description': 'High-performance vertical air termination rods, spikes, and ESE systems.',
        'display_order': 1,
        'is_active': True,
    }
)

sub_down_conductors, _ = SubCategory.objects.update_or_create(
    category=cat_lightning,
    code='DOWN_CONDUCTORS',
    defaults={
        'name': 'Down Conductors',
        'description': 'Conductors, tapes, and insulated down-lead systems.',
        'display_order': 2,
        'is_active': True,
    }
)

# Re-link existing products to proper category and subcategory
for p in Product.objects.all():
    if 'Compound' in p.name or p.sku == 'EXE-CEC-25KG':
        p.category = cat_earthing
        p.sub_category = sub_compounds
        p.save()
    elif 'Electrode' in p.name or 'CBR' in p.sku:
        p.category = cat_earthing
        p.sub_category = sub_electrodes
        p.save()
    elif 'Pit Cover' in p.name or 'EPC' in p.sku:
        p.category = cat_earthing
        p.sub_category = sub_pit_covers
        p.save()
    elif 'Lightning' in p.name or 'ESE' in p.sku:
        p.category = cat_lightning
        p.sub_category = sub_air_rods
        p.save()

# Add the specific products mentioned by the user if not present:
products_to_seed = [
    # Under Earth Compounds:
    {
        'name': 'Conductive Concrete',
        'sku': 'EXE-CC-01',
        'category': cat_earthing,
        'sub_category': sub_compounds,
        'price': 2400.00,
        'stock': 150,
        'description': 'Permanent, maintenance-free low resistivity conductive concrete for high-resistivity soil and rock.',
        'specifications': {
            'Resistivity': '< 0.05 Ohm-m in solid state',
            'Compressive Strength': '≥ 25 MPa at 28 days',
            'Corrosion Rate': 'Extremely low (anodic protection)',
            'Standard Compliance': 'IEC 62561-7 / IEEE 80',
            'Packaging': '25 kg moisture-proof bag'
        }
    },
    {
        'name': 'Electronically Charged Minerals',
        'sku': 'EXE-ECM-02',
        'category': cat_earthing,
        'sub_category': sub_compounds,
        'price': 2850.00,
        'stock': 120,
        'description': 'Engineered micro-minerals that release conductive ions continuously to maintain low soil resistance.',
        'specifications': {
            'Ionic Dissociation': 'Controlled continuous leaching',
            'pH Value': '7.2 - 8.5 (Non-corrosive)',
            'Thermal Conductivity': 'High heat dissipation during fault',
            'Service Life': 'Over 30 years',
            'Standard Compliance': 'IEEE 80 / IS 3043'
        }
    },
    {
        'name': 'A Fertiliser for Electrical Earthing',
        'sku': 'EXE-FEE-03',
        'category': cat_earthing,
        'sub_category': sub_compounds,
        'price': 1950.00,
        'stock': 200,
        'description': 'Special non-corrosive earthing fertiliser compound that conditions soil, improves moisture retention, and stabilizes earth resistance.',
        'specifications': {
            'Moisture Retention': 'Up to 300% dry weight',
            'Corrosion Inhibitors': 'Proprietary organic buffers',
            'Leach Rate': '< 1% annually under high rainfall',
            'Standard Compliance': 'IEC 62561-7 / IS 3043'
        }
    },
    # Under Vertical Air Termination Rods:
    {
        'name': 'Stainless Steel Multi Spike LA',
        'sku': 'EXE-SS-MS-LA',
        'category': cat_lightning,
        'sub_category': sub_air_rods,
        'price': 3800.00,
        'stock': 85,
        'description': 'Corrosion-resistant grade 316 stainless steel multi-spike air terminal for harsh industrial and coastal environments.',
        'specifications': {
            'Material Grade': 'AISI 316L Marine Stainless Steel',
            'Spike Configuration': '5-point multi-spike radial cluster',
            'Rod Diameter': '16mm / 20mm',
            'Overall Height': '1000mm - 2000mm options',
            'Standard Compliance': 'UL 96 / IEC 62305 / NFPA 780'
        }
    },
    {
        'name': 'Copper Bonded Multi Spike LA',
        'sku': 'EXE-CB-MS-LA',
        'category': cat_lightning,
        'sub_category': sub_air_rods,
        'price': 4200.00,
        'stock': 90,
        'description': 'High-purity molecularly bonded copper multi-spike lightning arrester terminal with superior electrical conductivity.',
        'specifications': {
            'Copper Coating': '≥ 254 Microns (99.9% Electrolytic Copper)',
            'Core Material': 'High tensile steel core (≥ 600 N/mm²)',
            'Spikes': '4 radial points + 1 center point',
            'Current Capacity': '100kA (10/350 µs waveform)',
            'Standard Compliance': 'IEC 62561-2 / UL 467'
        }
    }
]

for p_data in products_to_seed:
    prod, created = Product.objects.update_or_create(
        sku=p_data['sku'],
        defaults=p_data
    )
    status = "Created" if created else "Updated"
    print(f"Product {status}: {prod.name} ({prod.sku}) -> {prod.category.name} / {prod.sub_category.name}")

print("\n--- Summary of Categories & Subcategories ---")
for cat in Category.objects.all():
    print(f"\n[Category] {cat.name} ({cat.code}) - {cat.products.count()} total products")
    for sub in cat.subcategories.all():
        print(f"   └── [SubCategory] {sub.name} ({sub.code}) - {sub.products.count()} products")
        for prod in sub.products.all():
            print(f"         * {prod.name} ({prod.sku})")
