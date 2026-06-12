"""
python manage.py seed_demo         — create demo data (DEBUG only by default)
python manage.py seed_demo --wipe  — delete every seeded object and exit
python manage.py seed_demo --i-know-this-is-production  — override DEBUG guard

SAFETY RULE: every seeded user's phone starts with +88017000000 so wipe can
never accidentally touch real data.
"""

import io
import sys
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

User = get_user_model()

SEED_PHONE_PREFIX = '+88017000000'


# ---------------------------------------------------------------------------
# Static data
# ---------------------------------------------------------------------------

DEMO_USERS = [
    {'phone': '+8801700000001', 'full_name': 'রাফি হাসান', 'trust_level': 'verified'},
    {'phone': '+8801700000002', 'full_name': 'Tasnuva Akter', 'trust_level': 'verified'},
    {'phone': '+8801700000003', 'full_name': 'মাহমুদুল হক', 'trust_level': 'verified'},
    {'phone': '+8801700000004', 'full_name': 'Nadia Islam', 'trust_level': 'verified'},
    {'phone': '+8801700000005', 'full_name': 'শাহরিয়ার কবির', 'trust_level': 'verified'},
    {'phone': '+8801700000006', 'full_name': 'Fahmida Sultana', 'trust_level': 'verified'},
    {'phone': '+8801700000007', 'full_name': 'ইমরান খান', 'trust_level': 'verified'},
    {'phone': '+8801700000008', 'full_name': 'Sadia Rahman', 'trust_level': 'verified'},
    {'phone': '+8801700000009', 'full_name': 'তানভীর আহমেদ', 'trust_level': 'verified'},
    {'phone': '+8801700000010', 'full_name': 'Rumana Begum', 'trust_level': 'verified'},
    {'phone': '+8801700000011', 'full_name': 'নাফিস উদ্দিন', 'trust_level': 'verified'},
    {'phone': '+8801700000012', 'full_name': 'Maliha Hossain', 'trust_level': 'verified'},
    {'phone': '+8801700000013', 'full_name': 'আরিফুল ইসলাম', 'trust_level': 'verified'},
    {'phone': '+8801700000099', 'full_name': 'Bhara Official', 'trust_level': 'partner'},
]

# Staff/ops account — not a regular demo user, phone prefix still seeded
OPS_PHONE = '+8801700000098'
OPS_NAME = 'Bhara Ops'

PRODUCT_DATA = [
    # (title, category, product_type, location, status, day_price, deposit, desc)
    ('Canon EOS 1500D DSLR', 'photography_videography', 'camera',
     'Dhanmondi, Dhaka', 'active', 800, 5000,
     'Full kit with 18-55mm lens, battery, charger and bag.'),
    ('DJI Mavic Mini 2 ড্রোন', 'photography_videography', 'drone',
     'Banani, Dhaka', 'active', 1500, 10000,
     'Ultra-light drone with 4K camera. Extra batteries included.'),
    ('Sony A7III মিররলেস ক্যামেরা', 'photography_videography', 'camera',
     'Uttara, Dhaka', 'active', 2000, 15000,
     'Full-frame mirrorless with 28-70mm kit lens. Ideal for events and portraits.'),
    ('Zhiyun Crane 3 Gimbal', 'photography_videography', 'gimbal',
     'Dhanmondi, Dhaka', 'active', 600, 3000,
     '3-axis stabiliser for DSLR/mirrorless up to 4.5kg.'),
    ('ক্যাম্পিং তাঁবু ৪ জনের', 'camping_hiking', 'tent',
     'Mirpur, Dhaka', 'active', 500, 2000,
     'Waterproof 4-person dome tent. Easy to pitch. Good for Cox\'s Bazar trips.'),
    ('Decathlon Sleeping Bag', 'camping_hiking', 'sleeping_bag',
     'Mohammadpur, Dhaka', 'active', 200, 800,
     'Comfort temperature: 5°C. Fits up to 185cm.'),
    ('ট্রেকিং ব্যাকপ্যাক ৬০L', 'camping_hiking', 'backpack',
     'Uttara, Dhaka', 'active', 250, 1000,
     'Osprey Kestrel 60L with rain cover. Perfect for multi-day hikes.'),
    ('Samsonite 28" সুটকেস', 'travel_luggage', 'suitcase',
     'Banani, Dhaka', 'active', 300, 1500,
     'Hard-shell, TSA lock. Excellent for international travel.'),
    ('JBL Xtreme 2 ব্লুটুথ স্পিকার', 'event_party', 'sound_system',
     'Dhanmondi, Dhaka', 'active', 400, 2000,
     'Waterproof, 15-hour battery. Great for outdoor events.'),
    ('সাউন্ড সিস্টেম ইভেন্ট প্যাকেজ', 'event_party', 'sound_system',
     'Mirpur, Dhaka', 'active', 2500, 8000,
     '2× PA speakers, mixer, 2× mics. Suitable for 200-person events.'),
    ('Canon 50mm f/1.8 Lens', 'photography_videography', 'lens',
     'Mohammadpur, Dhaka', 'active', 300, 2000,
     'Nifty-fifty. Sharp bokeh. Canon EF mount.'),
    ('Rickshaw Bicycle হাইকিং সাইকেল', 'sports_outdoor', 'bicycle',
     'Uttara, Dhaka', 'active', 350, 1500,
     'Trek 21-speed mountain bike. Helmet included.'),
    ('Dell XPS 15 ল্যাপটপ', 'electronics', 'laptop',
     'Banani, Dhaka', 'active', 1200, 8000,
     'Core i7, 16GB RAM, 512GB SSD, GTX 1650Ti. Charger included.'),
    ('iPad Pro 11" (2022)', 'electronics', 'tablet',
     'Dhanmondi, Dhaka', 'active', 700, 5000,
     'M2 chip, 256GB, Wi-Fi. Apple Pencil 2nd gen included.'),
    ('Epson Projector EB-S41', 'electronics', 'projector',
     'Mirpur, Dhaka', 'active', 800, 3000,
     '3300 lumens, SVGA. HDMI & VGA. Ideal for presentations.'),
    ('DeWalt Drill Machine Set', 'tools_equipment', 'drill_machine',
     'Mohammadpur, Dhaka', 'active', 400, 2000,
     '18V cordless drill + driver bits set. Two batteries.'),
    ('বেহালা (Violin) 4/4', 'musical_instruments', 'violin',
     'Dhanmondi, Dhaka', 'active', 500, 3000,
     'Intermediate level. Comes with bow, rosin and case.'),
    ('Yamaha Keyboard PSR-E373', 'musical_instruments', 'keyboard',
     'Banani, Dhaka', 'active', 600, 2500,
     '61 keys, 622 voices. Adapter + sustain pedal included.'),
    # Draft — should not appear publicly
    ('GoPro Hero 11 (Draft)', 'photography_videography', 'camera',
     'Uttara, Dhaka', 'draft', 500, 3000,
     'Still setting up the listing.'),
    # Suspended — admin-moderated off
    ('Segway E-Scooter (Suspended)', 'sports_outdoor', 'sports_gear',
     'Banani, Dhaka', 'suspended', 600, 4000,
     'Temporarily suspended pending safety review.'),
    # A few more active to hit ~30
    ('ফরমাল শেরওয়ানি সেট', 'fashion_accessories', 'formal_wear',
     'Mirpur, Dhaka', 'active', 800, 3000,
     'XL size, navy blue. Ideal for weddings and Eid.'),
    ('Manfrotto Tripod 190X', 'photography_videography', 'tripod',
     'Dhanmondi, Dhaka', 'active', 250, 1200,
     'Carbon fibre, 190cm max height, ball head included.'),
    ('Camping Gas Stove & Cookset', 'camping_hiking', 'stove',
     'Uttara, Dhaka', 'active', 180, 600,
     'Compact butane stove + 2-piece aluminium cookset.'),
    ('Acoustic Guitar (Yamaha F310)', 'musical_instruments', 'guitar',
     'Mohammadpur, Dhaka', 'active', 350, 1500,
     'Dreadnought body. Tuner + extra strings included.'),
    ('Power Bank 20000mAh Anker', 'travel_luggage', 'power_bank',
     'Banani, Dhaka', 'active', 150, 500,
     '65W USB-C PD. Charges a laptop once fully.'),
    ('LED Stage Light Kit', 'event_party', 'stage_light',
     'Dhanmondi, Dhaka', 'active', 700, 2500,
     '4× moving head + controller. Great for stage shows.'),
    ('Sony ZV-E10 Vlog Camera', 'photography_videography', 'camera',
     'Mirpur, Dhaka', 'active', 900, 4000,
     'APS-C, detachable mic, kit lens 16-50mm. Great for YouTube.'),
    ('ল্যাডার ৮ ফুট অ্যালুমিনিয়াম', 'tools_equipment', 'ladder',
     'Mohammadpur, Dhaka', 'active', 200, 800,
     '8-foot foldable aluminium A-frame ladder. 150kg rated.'),
    ('Hiking Pole Pair (Black Diamond)', 'camping_hiking', 'hiking_pole',
     'Uttara, Dhaka', 'active', 150, 600,
     'Folding carbon poles, anti-shock. Pair with carrying bag.'),
    ('ট্যাবলেট Samsung Galaxy Tab S8', 'electronics', 'tablet',
     'Banani, Dhaka', 'active', 500, 3500,
     '11-inch AMOLED, 128GB. S-Pen included. Keyboard cover available.'),
]

# (reviewer_phone, reviewee_phone, rental_idx, rating, comment)
# rental_idx references the completed rentals we build below
REVIEW_DATA = [
    (5, 4, 'Canon EOS 1500D DSLR', 4, 'Camera was in perfect condition. Easy pickup.'),
    (5, 4, 'Canon EOS 1500D DSLR', 5, 'রাফি ভাই খুব যত্নসহকারে ক্যামেরা দিয়েছেন।'),
    (5, 4, 'Decathlon Sleeping Bag', 5, 'Very clean sleeping bag. Would rent again.'),
    (5, 4, 'Decathlon Sleeping Bag', 4, 'সময়মতো ফিরিয়ে দিয়েছে, ভালো রেন্টার।'),
    (5, 4, 'সাউন্ড সিস্টেম ইভেন্ট প্যাকেজ', 3, 'One mic had static. Otherwise fine.'),
    (5, 4, 'সাউন্ড সিস্টেম ইভেন্ট প্যাকেজ', 4, 'Used it carefully. No damage.'),
    (5, 4, 'Dell XPS 15 ল্যাপটপ', 5, 'Exactly as described. Highly recommended owner.'),
    (5, 4, 'Dell XPS 15 ল্যাপটপ', 5, 'ল্যাপটপ পরিষ্কার করে ফিরিয়ে দিয়েছে।'),
]


# ---------------------------------------------------------------------------
# Pillow image generation
# ---------------------------------------------------------------------------

CATEGORY_COLORS = {
    'photography_videography': (45, 62, 80),
    'sports_outdoor': (39, 174, 96),
    'camping_hiking': (146, 125, 88),
    'travel_luggage': (52, 152, 219),
    'event_party': (155, 89, 182),
    'fashion_accessories': (231, 76, 60),
    'electronics': (41, 128, 185),
    'tools_equipment': (127, 140, 141),
    'musical_instruments': (211, 84, 0),
    'other': (100, 100, 100),
}

# pastel: blend category colour with white 60%
def _pastel(rgb):
    return tuple(int(c * 0.4 + 255 * 0.6) for c in rgb)


def _make_product_image(category, title):
    """Return a PNG ContentFile (1200×900) with a pastel background and text overlay."""
    from PIL import Image, ImageDraw, ImageFont

    base_color = CATEGORY_COLORS.get(category, (100, 100, 100))
    bg = _pastel(base_color)
    img = Image.new('RGB', (1200, 900), color=bg)
    draw = ImageDraw.Draw(img)

    # Try to load a font; fall back to default if not available
    try:
        font_large = ImageFont.truetype('arial.ttf', 48)
        font_small = ImageFont.truetype('arial.ttf', 32)
    except (IOError, OSError):
        font_large = ImageFont.load_default()
        font_small = ImageFont.load_default()

    category_label = category.replace('_', ' ').title()
    text_color = tuple(int(c * 0.35) for c in bg)  # dark version of bg

    draw.text((60, 60), category_label, fill=text_color, font=font_small)
    # Wrap title at ~40 chars
    words = title.split()
    lines, line = [], []
    for w in words:
        line.append(w)
        if len(' '.join(line)) > 30:
            lines.append(' '.join(line[:-1]))
            line = [w]
    lines.append(' '.join(line))
    y = 380
    for l in lines:
        draw.text((60, y), l, fill=text_color, font=font_large)
        y += 60

    buf = io.BytesIO()
    img.save(buf, format='PNG', optimize=True)
    return ContentFile(buf.getvalue(), name='demo.png')


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = 'Seed demo data for Bhara (DEBUG environments only by default).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--wipe',
            action='store_true',
            help='Delete all seeded objects and exit.',
        )
        parser.add_argument(
            '--i-know-this-is-production',
            action='store_true',
            dest='force_prod',
            help='Override the DEBUG guard. You take responsibility.',
        )

    def handle(self, *args, **options):
        if not settings.DEBUG and not options['force_prod']:
            raise CommandError(
                '\n'
                '╔══════════════════════════════════════════════════════╗\n'
                '║  REFUSED: DEBUG is False.                            ║\n'
                '║  This command seeds test data into the database.     ║\n'
                '║  If you REALLY mean to run on production, pass:      ║\n'
                '║    --i-know-this-is-production                       ║\n'
                '╚══════════════════════════════════════════════════════╝'
            )

        if not settings.DEBUG and options['force_prod']:
            self.stderr.write(self.style.WARNING(
                '\n⚠️  WARNING: Running seed_demo on a PRODUCTION database!\n'
                '   All seeded users have phones starting with +88017000000.\n'
                '   Use --wipe to remove them later.\n'
            ))

        if options['wipe']:
            self._wipe()
            return

        self._seed()

    # ------------------------------------------------------------------

    def _wipe(self):
        from listings.models import Product, ProductImage
        from rentals.models import Rental, PaymentRecord
        from reviews.models import Review

        seed_users = User.objects.filter(phone_number__startswith=SEED_PHONE_PREFIX)
        seed_user_ids = list(seed_users.values_list('id', flat=True))

        with transaction.atomic():
            Review.objects.filter(reviewer_id__in=seed_user_ids).delete()
            PaymentRecord.objects.filter(rental__owner_id__in=seed_user_ids).delete()
            Rental.objects.filter(owner_id__in=seed_user_ids).delete()
            Product.objects.filter(owner_id__in=seed_user_ids).delete()
            n = seed_users.count()
            seed_users.delete()

        self.stdout.write(self.style.SUCCESS(
            f'Wiped all seeded data ({n} users + their products/rentals/reviews).'
        ))

    # ------------------------------------------------------------------

    @transaction.atomic
    def _seed(self):
        from listings.models import Product, ProductImage, PricingTier
        from rentals.models import Rental, PaymentRecord, compute_end_date
        from reviews.models import Review

        # ---- ops staff user (not in DEMO_USERS list, but same prefix) ----
        ops_user, _ = User.objects.get_or_create(
            phone_number=OPS_PHONE,
            defaults={
                'full_name': OPS_NAME,
                'trust_level': 'partner',
                'profile_completed': True,
                'is_staff': True,
                'is_approved': True,
            },
        )
        ops_user.set_password('demo1234')
        ops_user.save(update_fields=['password'])

        # ---- regular demo users ----
        users = []
        for u in DEMO_USERS:
            user, _ = User.objects.get_or_create(
                phone_number=u['phone'],
                defaults={
                    'full_name': u['full_name'],
                    'trust_level': u['trust_level'],
                    'profile_completed': True,
                    'is_approved': True,
                    'date_of_birth': date(1992, 1, 1),
                    'district': 'Dhaka',
                    'thana': 'Dhanmondi',
                    'full_address': '123 Demo Street, Dhaka',
                },
            )
            user.set_password('demo1234')
            user.save(update_fields=['password'])
            users.append(user)

        # users[0..12] = regular verified; users[13] = Bhara Official (partner)
        # Assign owners: spread products across first 10 users
        owners = users[:10]

        # ---- products ----
        products = {}  # title → Product
        for i, pd in enumerate(PRODUCT_DATA):
            title, category, ptype, location, status, day_price, deposit, desc = pd
            owner = owners[i % len(owners)]
            product, created = Product.objects.get_or_create(
                title=title,
                owner=owner,
                defaults={
                    'category': category,
                    'product_type': ptype,
                    'description': desc,
                    'location': location,
                    'security_deposit': Decimal(str(deposit)),
                    'purchase_year': '2022',
                    'original_price': Decimal(str(day_price * 300)),
                    'ownership_history': 'firsthand',
                    'status': status,
                },
            )
            if created:
                # Pricing tiers
                PricingTier.objects.get_or_create(
                    product=product, duration_unit='day',
                    defaults={'price': day_price, 'max_period': 30},
                )
                week_price = day_price * 6  # slight discount
                PricingTier.objects.get_or_create(
                    product=product, duration_unit='week',
                    defaults={'price': week_price, 'max_period': 8},
                )
                month_price = day_price * 22
                PricingTier.objects.get_or_create(
                    product=product, duration_unit='month',
                    defaults={'price': month_price, 'max_period': 6},
                )
                # Generate 2 images
                for _ in range(2):
                    img_file = _make_product_image(category, title)
                    pi = ProductImage(product=product)
                    pi.image.save('demo.png', img_file, save=True)

            products[title] = product

        # ---- rentals ----
        # We'll build rentals covering all 6 statuses.
        # Renters are users[10..12] (the 3 non-owner verified users) and a couple of owners
        # renting from each other — just pick renters != owner per rental.
        today = date.today()

        def _make_rental(product_title, renter, status_path, start, duration,
                         duration_unit='day', purpose='personal', notes=''):
            """
            Create a rental and walk it through status_path via transition().
            status_path: list of (new_status, actor) tuples after 'pending'.
            Returns the Rental instance.
            """
            product = products[product_title]
            tier = product.pricing_tiers.get(duration_unit=duration_unit)
            unit_price = Decimal(str(tier.price))
            base_cost = unit_price * duration
            service_fee = (base_cost * settings.SERVICE_FEE_RATE).quantize(Decimal('0.01'))
            owner_payout = base_cost - service_fee
            end = compute_end_date(start, duration, duration_unit)
            now_ts = timezone.now().isoformat()
            rental, created = Rental.objects.get_or_create(
                product=product,
                renter=renter,
                start_date=start,
                defaults={
                    'owner': product.owner,
                    'end_date': end,
                    'duration': duration,
                    'duration_unit': duration_unit,
                    'unit_price': unit_price,
                    'base_cost': base_cost,
                    'service_fee': service_fee,
                    'owner_payout': owner_payout,
                    'security_deposit': product.security_deposit,
                    'purpose': purpose,
                    'notes': notes,
                    'status': 'pending',
                    'status_history': [{
                        'status': 'pending',
                        'timestamp': now_ts,
                        'actor_id': str(renter.pk),
                        'note': '',
                    }],
                },
            )
            if created:
                for new_status, actor in status_path:
                    rental.transition(new_status, actor)
            return rental

        def _pay(rental, rent_method='cash'):
            """Add the PaymentRecords required before completing a rental."""
            base = rental.base_cost
            dep = rental.security_deposit
            payout = rental.owner_payout
            PaymentRecord.objects.get_or_create(
                rental=rental, record_type='rent_collected',
                defaults={'amount': base, 'method': rent_method,
                          'reference': '', 'note': '', 'recorded_by': ops_user},
            )
            if dep > 0:
                PaymentRecord.objects.get_or_create(
                    rental=rental, record_type='deposit_collected',
                    defaults={'amount': dep, 'method': rent_method,
                              'reference': '', 'note': '', 'recorded_by': ops_user},
                )
                PaymentRecord.objects.get_or_create(
                    rental=rental, record_type='deposit_returned',
                    defaults={'amount': dep, 'method': rent_method,
                              'reference': '', 'note': '', 'recorded_by': ops_user},
                )
            PaymentRecord.objects.get_or_create(
                rental=rental, record_type='owner_payout',
                defaults={'amount': payout, 'method': rent_method,
                          'reference': '', 'note': '', 'recorded_by': ops_user},
            )

        renter_a = users[10]  # নাফিস উদ্দিন
        renter_b = users[11]  # Maliha Hossain
        renter_c = users[12]  # আরিফুল ইসলাম

        # --- COMPLETED rentals (in the past) ---
        comp1 = _make_rental(
            'Canon EOS 1500D DSLR', renter_a,
            [('accepted', products['Canon EOS 1500D DSLR'].owner),
             ('in_progress', ops_user)],
            start=today - timedelta(days=20), duration=3,
        )
        _pay(comp1)
        if comp1.status == 'in_progress':
            comp1.transition('completed', ops_user)

        comp2 = _make_rental(
            'Decathlon Sleeping Bag', renter_b,
            [('accepted', products['Decathlon Sleeping Bag'].owner),
             ('in_progress', ops_user)],
            start=today - timedelta(days=30), duration=5,
        )
        _pay(comp2)
        if comp2.status == 'in_progress':
            comp2.transition('completed', ops_user)

        comp3 = _make_rental(
            'সাউন্ড সিস্টেম ইভেন্ট প্যাকেজ', renter_c,
            [('accepted', products['সাউন্ড সিস্টেম ইভেন্ট প্যাকেজ'].owner),
             ('in_progress', ops_user)],
            start=today - timedelta(days=15), duration=2,
        )
        _pay(comp3)
        if comp3.status == 'in_progress':
            comp3.transition('completed', ops_user)

        comp4 = _make_rental(
            'Dell XPS 15 ল্যাপটপ', renter_a,
            [('accepted', products['Dell XPS 15 ল্যাপটপ'].owner),
             ('in_progress', ops_user)],
            start=today - timedelta(days=45), duration=7,
        )
        _pay(comp4)
        if comp4.status == 'in_progress':
            comp4.transition('completed', ops_user)

        # --- IN_PROGRESS (spanning today) ---
        _make_rental(
            'DJI Mavic Mini 2 ড্রোন', renter_b,
            [('accepted', products['DJI Mavic Mini 2 ড্রোন'].owner),
             ('in_progress', ops_user)],
            start=today - timedelta(days=2), duration=5,
        )

        _make_rental(
            'Epson Projector EB-S41', renter_c,
            [('accepted', products['Epson Projector EB-S41'].owner),
             ('in_progress', ops_user)],
            start=today - timedelta(days=1), duration=3,
        )

        # --- ACCEPTED (future) ---
        _make_rental(
            'Sony A7III মিররলেস ক্যামেরা', renter_a,
            [('accepted', products['Sony A7III মিররলেস ক্যামেরা'].owner)],
            start=today + timedelta(days=5), duration=4,
        )

        _make_rental(
            'iPad Pro 11" (2022)', renter_b,
            [('accepted', products['iPad Pro 11" (2022)'].owner)],
            start=today + timedelta(days=3), duration=2,
        )

        # --- PENDING ---
        _make_rental(
            'ক্যাম্পিং তাঁবু ৪ জনের', renter_c,
            [],
            start=today + timedelta(days=10), duration=3,
        )

        _make_rental(
            'Yamaha Keyboard PSR-E373', renter_a,
            [],
            start=today + timedelta(days=7), duration=7, duration_unit='day',
        )

        _make_rental(
            'JBL Xtreme 2 ব্লুটুথ স্পিকার', renter_b,
            [],
            start=today + timedelta(days=4), duration=2,
        )

        # --- REJECTED ---
        _make_rental(
            'Canon 50mm f/1.8 Lens', renter_c,
            [('rejected', products['Canon 50mm f/1.8 Lens'].owner)],
            start=today + timedelta(days=8), duration=2,
        )

        # --- CANCELLED ---
        _make_rental(
            'Manfrotto Tripod 190X', renter_a,
            [('accepted', products['Manfrotto Tripod 190X'].owner),
             ('cancelled', renter_a)],
            start=today + timedelta(days=12), duration=3,
        )

        # ---- reviews ----
        completed_rentals = {
            'Canon EOS 1500D DSLR': comp1,
            'Decathlon Sleeping Bag': comp2,
            'সাউন্ড সিস্টেম ইভেন্ট প্যাকেজ': comp3,
            'Dell XPS 15 ল্যাপটপ': comp4,
        }

        review_pairs = [
            # (product_title, renter, owner, renter_rating, owner_rating,
            #  renter_comment, owner_comment)
            ('Canon EOS 1500D DSLR', renter_a,
             products['Canon EOS 1500D DSLR'].owner,
             4, 5,
             'Camera was in perfect condition. Easy pickup.',
             'রাফি ভাই খুব সময়মতো ফিরিয়ে দিয়েছেন। আবার ভাড়া দেব।'),
            ('Decathlon Sleeping Bag', renter_b,
             products['Decathlon Sleeping Bag'].owner,
             5, 4,
             'Very clean sleeping bag. Would rent again.',
             'সময়মতো ফিরিয়ে দিয়েছে, ভালো রেন্টার।'),
            ('সাউন্ড সিস্টেম ইভেন্ট প্যাকেজ', renter_c,
             products['সাউন্ড সিস্টেম ইভেন্ট প্যাকেজ'].owner,
             3, 4,
             'One mic had static. Otherwise fine for the event.',
             'Used it carefully. No visible damage. Good renter.'),
            ('Dell XPS 15 ল্যাপটপ', renter_a,
             products['Dell XPS 15 ল্যাপটপ'].owner,
             5, 5,
             'Exactly as described. Highly recommended owner.',
             'ল্যাপটপ পরিষ্কার করে ফিরিয়ে দিয়েছে। Perfect.'),
        ]

        for product_title, renter, owner, r_rating, o_rating, r_comment, o_comment in review_pairs:
            rental = completed_rentals[product_title]
            # renter → owner
            Review.objects.get_or_create(
                rental=rental, reviewer=renter,
                defaults={
                    'reviewee': owner,
                    'product': rental.product,
                    'direction': 'renter_to_owner',
                    'rating': r_rating,
                    'comment': r_comment,
                },
            )
            # owner → renter
            Review.objects.get_or_create(
                rental=rental, reviewer=owner,
                defaults={
                    'reviewee': renter,
                    'product': rental.product,
                    'direction': 'owner_to_renter',
                    'rating': o_rating,
                    'comment': o_comment,
                },
            )

        # ---- summary ----
        self._print_summary()

    def _print_summary(self):
        from listings.models import Product
        from rentals.models import Rental
        from reviews.models import Review

        seed_user_qs = User.objects.filter(phone_number__startswith=SEED_PHONE_PREFIX)
        user_count = seed_user_qs.count()
        product_count = Product.objects.filter(owner__in=seed_user_qs).count()

        rental_qs = Rental.objects.filter(owner__in=seed_user_qs)
        status_counts = {}
        for status, _ in [('pending',''), ('accepted',''), ('in_progress',''),
                          ('completed',''), ('rejected',''), ('cancelled','')]:
            status_counts[status] = rental_qs.filter(status=status).count()

        review_count = Review.objects.filter(reviewer__in=seed_user_qs).count()

        self.stdout.write(self.style.SUCCESS('\n✓ Demo data seeded successfully!\n'))
        self.stdout.write('┌─────────────────────────────────────┐')
        self.stdout.write(f'│  Users (seeded)   : {user_count:<17}│')
        self.stdout.write(f'│  Products         : {product_count:<17}│')
        self.stdout.write(f'│  Rentals total    : {rental_qs.count():<17}│')
        for s, c in status_counts.items():
            self.stdout.write(f'│    {s:<16}: {c:<15}│')
        self.stdout.write(f'│  Reviews          : {review_count:<17}│')
        self.stdout.write('└─────────────────────────────────────┘')

        self.stdout.write('\nDemo login credentials (password: demo1234):')
        for u in DEMO_USERS:
            self.stdout.write(f'  {u["phone"]}  {u["full_name"]}')
        self.stdout.write(f'  {OPS_PHONE}  {OPS_NAME} (staff)')
