"""
BRAND: An Post Insurance Quote Calculation Service
Irish car insurance pricing formulas and tier definitions

CONFIG MARKERS: All constants will become configurator inputs
"""

from typing import List, Dict, Optional
from pydantic import BaseModel
import random

# BRAND: An Post's panel of insurers
INSURERS = ['Aviva', 'Allianz', 'AIG', 'FBD']

# BRAND: Base annual rates for An Post car insurance
BASE_RATES = {
    'car': {
        'comprehensive': 400,  # Average comprehensive annual premium
        'tpft': 250,          # Third Party Fire & Theft
    }
}

# BRAND: No Claims Discount levels (FBD offers up to 75%)
NCD_LEVELS = [0, 5, 10, 15, 20, 30, 40, 50, 60, 70, 75]

# BRAND: Age multipliers for Irish market
AGE_MULTIPLIERS = {
    '17-24': 2.5,   # Young drivers - higher risk
    '25-34': 1.4,
    '35-49': 1.0,   # Base rate
    '50-64': 0.9,   # Experienced drivers
    '65+': 1.1,
}

# BRAND: An Post optional extras with Irish pricing
EXTRAS = [
    {'id': 'motor_legal', 'name': 'Motor Legal Protection', 'price': 15.00, 'description': 'Legal expenses up to €100,000'},
    {'id': 'keycare', 'name': 'Keycare', 'price': 19.95, 'description': 'Lost or stolen key replacement (incl. govt levy)'},
    {'id': 'open_drive', 'name': 'Open Drive', 'price': 50.00, 'description': 'Allow any eligible driver over 25'},
    {'id': 'protected_ncd', 'name': 'Protected NCD', 'price': 30.00, 'description': 'Protect your no claims discount'},
]

# BRAND: Tier definitions for An Post car insurance
TIER_DEFINITIONS = {
    'car': [
        {
            'id': 'tpft',
            'name': 'Third Party Fire & Theft',
            'tagline': 'Essential cover at a lower price',
            'coverage_type': 'tpft',
            'recommended': False,
            'features': [
                'Third party liability',
                'Fire damage',
                'Theft protection',
                '24h Breakdown Assistance',
                'European cover (31-60 days)',
            ],
        },
        {
            'id': 'comprehensive',
            'name': 'Comprehensive',
            'tagline': 'Complete protection for your vehicle',
            'coverage_type': 'comprehensive',
            'recommended': True,
            'features': [
                'All TPFT benefits',
                'Damage to your own car',
                'Windscreen cover (unlimited)',
                'Personal belongings (€150-€775)',
                'European cover (31-60 days)',
                '24h Breakdown Assistance',
            ],
        },
    ]
}


# Pydantic Models
class VehicleDetails(BaseModel):
    make: str
    model: str
    year: int


class QuoteParams(BaseModel):
    product_type: str = 'car'
    coverage_type: str  # 'comprehensive' or 'tpft'
    driver_age: int
    ncd_years: int
    vehicle: VehicleDetails
    extras: List[str] = []


class TierQuote(BaseModel):
    id: str
    name: str
    tagline: str
    monthly_price: int
    annual_price: int
    original_price: int
    online_discount: float
    recommended: bool
    features: List[str]


class InsurerQuote(BaseModel):
    insurer: str
    monthly_price: int
    annual_price: int
    recommended: bool = False


class QuoteResult(BaseModel):
    product_type: str
    vehicle: VehicleDetails
    driver_age: int
    ncd_years: int
    coverage_type: str
    tiers: List[TierQuote]
    insurer_panel: List[InsurerQuote]


# Helper Functions
def get_age_multiplier(age: int) -> float:
    """Get age-based multiplier for Irish insurance market"""
    if age < 25:
        return AGE_MULTIPLIERS['17-24']
    elif age < 35:
        return AGE_MULTIPLIERS['25-34']
    elif age < 50:
        return AGE_MULTIPLIERS['35-49']
    elif age < 65:
        return AGE_MULTIPLIERS['50-64']
    else:
        return AGE_MULTIPLIERS['65+']


def apply_online_discount(price: float) -> Dict[str, float]:
    """
    BRAND: Apply An Post's online discount
    15% OR €80, whichever is LOWER (new business only)
    """
    discount = min(price * 0.15, 80.0)
    return {
        'discounted_price': round(price - discount, 2),
        'discount_amount': round(discount, 2),
    }


def calculate_tier_price(coverage_type: str, driver_age: int, ncd_years: int) -> float:
    """
    Calculate car insurance price with Irish multipliers
    Returns annual price before online discount
    """
    base_price = BASE_RATES['car'].get(coverage_type, BASE_RATES['car']['comprehensive'])

    # Apply age multiplier
    age_multiplier = get_age_multiplier(driver_age)
    price = base_price * age_multiplier

    # Apply NCD discount (0-75% for FBD)
    ncd_index = min(ncd_years, len(NCD_LEVELS) - 1)
    ncd_percent = NCD_LEVELS[ncd_index]
    price *= (1 - ncd_percent / 100)

    return round(price, 2)


def generate_tier_quotes(params: QuoteParams) -> List[TierQuote]:
    """
    Generate quote tiers for car insurance
    Returns pricing for both tiers with online discount applied
    """
    tiers = TIER_DEFINITIONS[params.product_type]
    tier_quotes = []

    for tier in tiers:
        # Calculate base price with factors
        annual_price = calculate_tier_price(
            tier['coverage_type'],
            params.driver_age,
            params.ncd_years
        )

        # Apply online discount (15% or €80 cap)
        discount_result = apply_online_discount(annual_price)
        discounted_price = discount_result['discounted_price']
        discount_amount = discount_result['discount_amount']

        # Monthly = annual / 12
        monthly_price = round(discounted_price / 12)

        tier_quotes.append(TierQuote(
            id=tier['id'],
            name=tier['name'],
            tagline=tier['tagline'],
            monthly_price=monthly_price,
            annual_price=round(discounted_price),
            original_price=round(annual_price),
            online_discount=discount_amount,
            recommended=tier['recommended'],
            features=tier['features']
        ))

    return tier_quotes


def generate_insurer_panel(base_annual_price: float) -> List[InsurerQuote]:
    """
    BRAND: Generate 4-insurer panel with price variance
    Simulates An Post's multi-insurer panel (Aviva, Allianz, AIG, FBD)
    """
    insurer_quotes = []

    for idx, insurer in enumerate(INSURERS):
        # Add 5-15% variance to simulate different insurers
        variance_percent = 0.05 + random.random() * 0.10
        variance = 1 + variance_percent * (1 if idx % 2 == 0 else -1)
        price = base_annual_price * variance

        insurer_quotes.append(InsurerQuote(
            insurer=insurer,
            monthly_price=round(price / 12),
            annual_price=round(price),
            recommended=False
        ))

    # Sort by price (lowest first)
    insurer_quotes.sort(key=lambda x: x.annual_price)

    # Mark lowest price as recommended
    if insurer_quotes:
        insurer_quotes[0].recommended = True

    return insurer_quotes


def calculate_quote(params: QuoteParams) -> QuoteResult:
    """
    Main quote calculation function
    Returns complete quote with tiers and insurer panel
    """
    # Generate tier quotes (both TPFT and Comprehensive)
    tier_quotes = generate_tier_quotes(params)

    # Find the selected coverage tier for insurer panel generation
    selected_tier = next(
        (tier for tier in tier_quotes if tier.id == params.coverage_type),
        tier_quotes[0]  # Default to first tier if not found
    )

    # Generate insurer panel based on selected tier price
    insurer_panel = generate_insurer_panel(selected_tier.annual_price)

    return QuoteResult(
        product_type=params.product_type,
        vehicle=params.vehicle,
        driver_age=params.driver_age,
        ncd_years=params.ncd_years,
        coverage_type=params.coverage_type,
        tiers=tier_quotes,
        insurer_panel=insurer_panel
    )


def get_extras() -> List[Dict]:
    """Return available optional extras"""
    return EXTRAS


def get_tier_definitions(product_type: str = 'car') -> List[Dict]:
    """Return tier definitions for a product type"""
    return TIER_DEFINITIONS.get(product_type, [])
