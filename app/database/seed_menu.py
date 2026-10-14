"""
Database seeder: populates MenuItem table with Dhaka Spice House dishes.
Ensures the database is the authoritative source of truth for pricing and availability.
"""
from decimal import Decimal
from app.database.database import SessionLocal, init_db
from app.database.models import MenuItem
from app.utils.logger import get_logger

log = get_logger(__name__)

SAMPLE_MENU = [
    # Mains / Biryani
    {
        "item_code": "mains-kachchi-biryani-mutton",
        "name": "Kachchi Biryani (Mutton)",
        "category": "Biryani & Mains",
        "description": "Traditional aromatic basmati rice cooked with tender marinated mutton chunks, saffron, and spiced potatoes. Served with salad.",
        "price": Decimal("350.00"),
        "is_available": True,
    },
    {
        "item_code": "mains-chicken-biryani",
        "name": "Chicken Biryani",
        "category": "Biryani & Mains",
        "description": "Fragrant basmati rice layered with slow-cooked spiced chicken, caramelized onions, and boiled egg.",
        "price": Decimal("260.00"),
        "is_available": True,
    },
    {
        "item_code": "mains-beef-tehari",
        "name": "Old Dhaka Beef Tehari",
        "category": "Biryani & Mains",
        "description": "Traditional Chinigura rice infused with pure mustard oil, green chillies, and tender bite-sized beef.",
        "price": Decimal("240.00"),
        "is_available": True,
    },
    {
        "item_code": "mains-chicken-khichuri",
        "name": "Chicken Bhuna Khichuri",
        "category": "Biryani & Mains",
        "description": "Rich roasted moong dal and Chinigura rice cooked with spicy bhuna chicken curry.",
        "price": Decimal("230.00"),
        "is_available": True,
    },
    # Kebabs & Grills
    {
        "item_code": "kebabs-chicken-tikka",
        "name": "Chicken Tikka Kebab (4 pcs)",
        "category": "Kebabs & Grills",
        "description": "Boneless chicken thighs marinated in yogurt, Kashmiri chilli, and tandoori spices, char-grilled to perfection.",
        "price": Decimal("180.00"),
        "is_available": True,
    },
    {
        "item_code": "kebabs-beef-sheekh",
        "name": "Beef Sheekh Kebab (2 pcs)",
        "category": "Kebabs & Grills",
        "description": "Minced beef infused with ginger, garlic, coriander, and freshly roasted garam masala skewers.",
        "price": Decimal("190.00"),
        "is_available": True,
    },
    # Wings & Appetizers
    {
        "item_code": "appetizer-crispy-wings-6",
        "name": "Crispy Naga Wings (6 pcs)",
        "category": "Wings & Appetizers",
        "description": "Extra crunchy chicken wings tossed in our signature spicy Naga chilli glaze.",
        "price": Decimal("220.00"),
        "is_available": True,
    },
    {
        "item_code": "appetizer-honey-garlic-wings",
        "name": "Honey Garlic Glazed Wings (6 pcs)",
        "category": "Wings & Appetizers",
        "description": "Crispy fried wings tossed in sweet honey, roasted garlic, and sesame seeds.",
        "price": Decimal("210.00"),
        "is_available": True,
    },
    # Drinks
    {
        "item_code": "drinks-special-borhani-500ml",
        "name": "Special Borhani (500ml)",
        "category": "Drinks",
        "description": "Refreshing traditional spiced yogurt beverage blended with mint, coriander, mustard, and black salt.",
        "price": Decimal("90.00"),
        "is_available": True,
    },
    {
        "item_code": "drinks-mango-lassi",
        "name": "Mango Lassi",
        "category": "Drinks",
        "description": "Thick creamy yogurt smoothie made with sweet Alfonso mango pulp.",
        "price": Decimal("120.00"),
        "is_available": True,
    },
    {
        "item_code": "drinks-fresh-lemon-mint",
        "name": "Fresh Lemon Mint Cooler",
        "category": "Drinks",
        "description": "Chilled sparkling limeade with crushed fresh garden mint and rock salt.",
        "price": Decimal("70.00"),
        "is_available": True,
    },
    {
        "item_code": "drinks-coca-cola-can",
        "name": "Coca-Cola (330ml Can)",
        "category": "Drinks",
        "description": "Chilled can of Coca-Cola.",
        "price": Decimal("40.00"),
        "is_available": True,
    },
    # Desserts
    {
        "item_code": "dessert-shahi-firni",
        "name": "Shahi Firni (Clay Cup)",
        "category": "Desserts",
        "description": "Slow-cooked creamy rice pudding with rich milk, cardamom, saffron, pistachios, and almonds.",
        "price": Decimal("60.00"),
        "is_available": True,
    },
    {
        "item_code": "dessert-gulab-jamun-2",
        "name": "Hot Gulab Jamun (2 pcs)",
        "category": "Desserts",
        "description": "Soft khoya milk dumplings fried to golden brown and soaked in rose-infused sugar syrup.",
        "price": Decimal("70.00"),
        "is_available": True,
    },
]


def seed_menu():
    """Initializes database and seeds standard menu items if empty."""
    init_db()
    db = SessionLocal()
    try:
        existing_count = db.query(MenuItem).count()
        if existing_count == 0:
            log.info("Seeding menu_items table with %d dishes...", len(SAMPLE_MENU))
            for item_data in SAMPLE_MENU:
                item = MenuItem(**item_data)
                db.add(item)
            db.commit()
            log.info("Menu successfully seeded.")
        else:
            log.info("Menu already contains %d items; skipping seed.", existing_count)
    finally:
        db.close()


if __name__ == "__main__":
    seed_menu()
