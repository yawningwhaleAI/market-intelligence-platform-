"""Small, transparent product-scope suggestions for first-time founders.

These rules are deliberately a starting point, not a claim about demand or
market size. A future AI provider can extend this response without changing
the wizard contract.
"""
from __future__ import annotations

PROFILES: tuple[tuple[tuple[str, ...], dict], ...] = (
    (("skincare", "skin care", "serum", "moisturizer", "sunscreen", "face wash", "beauty"), {
        "family": "Beauty & personal care",
        "segments": ["Cleansers", "Serums & treatments", "Moisturizers", "Sun protection", "Masks & exfoliants"],
        "attributes": ["Skin concern", "Active ingredients", "Formula and texture", "Skin type", "SPF / protection", "Pack size and price per ml"],
        "terms": ["face serum", "face moisturizer", "face cleanser", "sunscreen", "skin treatment"],
    }),
    (("protein", "snack", "food", "beverage", "drink", "coffee", "tea", "nutrition", "supplement"), {
        "family": "Food, drink & nutrition",
        "segments": ["Core product", "Flavours and variants", "High-protein / functional options", "Trial packs", "Multipacks"],
        "attributes": ["Ingredients", "Dietary claims", "Flavour", "Pack size", "Price per serving", "Nutrition claims"],
        "terms": ["protein snack", "high protein food", "healthy snack", "functional beverage", "nutrition drink"],
    }),
    (("cleaner", "detergent", "laundry", "dishwash", "cleaning", "home care", "surface"), {
        "family": "Home care & cleaning",
        "segments": ["Laundry care", "Dish care", "Surface cleaners", "Specialist cleaners", "Refills and concentrates"],
        "attributes": ["Use case", "Format", "Ingredients", "Scent", "Concentration / dose", "Price per use"],
        "terms": ["laundry detergent", "dish wash", "surface cleaner", "cleaning spray", "cleaner refill"],
    }),
    (("tissue", "paper towel", "napkin", "toilet paper", "wet wipe", "wipes"), {
        "family": "Tissue, paper & wipes",
        "segments": ["Facial tissue", "Kitchen towels", "Toilet rolls", "Paper napkins", "Wet wipes"],
        "attributes": ["Ply / layers", "Sheet or roll count", "Sheet dimensions", "Material", "Use case", "Price per 100 sheets"],
        "terms": ["facial tissue", "kitchen towel", "toilet paper", "paper napkins", "wet wipes"],
    }),
    (("pet", "dog", "cat", "puppy", "kitten"), {
        "family": "Pet care",
        "segments": ["Food and treats", "Grooming", "Health and supplements", "Hygiene", "Accessories"],
        "attributes": ["Pet type / life stage", "Ingredients", "Pack size", "Use case", "Price per serving", "Claims"],
        "terms": ["dog food", "cat food", "pet treats", "pet grooming", "pet supplements"],
    }),
    (("baby", "infant", "maternity", "mom", "mother"), {
        "family": "Baby & mom care",
        "segments": ["Diapers", "Baby skin care", "Feeding", "Baby wipes", "Mom care"],
        "attributes": ["Age / size stage", "Ingredients", "Pack count", "Material", "Use case", "Price per unit"],
        "terms": ["baby diapers", "baby wipes", "baby lotion", "baby wash", "maternity care"],
    }),
    (("apparel", "clothing", "fashion", "wear", "t-shirt", "kurta", "footwear"), {
        "family": "Apparel & accessories",
        "segments": ["Core product", "Styles and fits", "Everyday essentials", "Premium range", "Accessories"],
        "attributes": ["Material", "Fit / size range", "Use occasion", "Style", "Price band", "Pack / set options"],
        "terms": ["everyday apparel", "premium clothing", "cotton clothing", "activewear", "fashion accessories"],
    }),
)

GENERIC = {
    "family": "General consumer product",
    "segments": ["Core product", "Formats and variants", "Entry / trial size", "Premium option", "Refill / multipack"],
    "attributes": ["Main use case", "Material / ingredients", "Size or quantity", "Price per unit", "Key product claims", "Packaging format"],
    "terms": ["product type", "product type best seller", "product type multipack", "product type premium", "product type refill"],
}


def suggest_scope(product: str, industry: str = "", segments: list[str] | None = None) -> dict:
    """Return editable category and query candidates based on the user brief."""
    text = " ".join([product, industry, *(segments or [])]).casefold().strip()
    chosen = next((profile for tokens, profile in PROFILES if any(token in text for token in tokens)), GENERIC)
    base = (product or (segments or [""])[0] or "product").strip()
    terms = [term.replace("product type", base) for term in chosen["terms"]]
    if base and base.casefold() not in chosen["family"].casefold():
        # Keep one query close to the founder's own words, then provide adjacent discovery angles.
        terms.insert(0, base)
    return {
        "category_family": chosen["family"],
        "summary": f"A starting checklist for {chosen['family'].lower()}. Keep only what matches your product and customer.",
        "suggested_segments": chosen["segments"],
        "comparison_attributes": chosen["attributes"],
        "search_phrases": list(dict.fromkeys(terms))[:10],
        "research_angles": [
            {"id": "assortment", "label": "Products and variants", "detail": "Compare formats, sizes, and adjacent product lines."},
            {"id": "pricing", "label": "Price and pack value", "detail": "Compare price bands and unit value when listing data supports it."},
            {"id": "competition", "label": "Brands and substitutes", "detail": "Identify brands and alternatives appearing in selected marketplace results."},
            {"id": "promotions", "label": "Promotions", "detail": "Track visible discounts and offer labels when the source exposes them."},
        ],
        "confidence": "category template" if chosen is not GENERIC else "general template",
        "note": "Suggestions are prompts for your research plan, not evidence of demand. Marketplace results and supported fields vary by source.",
    }
