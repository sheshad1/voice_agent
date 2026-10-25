"""Service-area catalogue. Centre names are sample data for the pilot."""

CENTRES: dict[str, tuple[str, ...]] = {
    "Bengaluru": ("Koramangala Centre", "Whitefield Centre"),
    "Hyderabad": ("Madhapur Centre", "Kukatpally Centre"),
    "Mumbai": ("Andheri Centre", "Thane Centre"),
    "Delhi": ("Saket Centre", "Dwarka Centre"),
    "Chennai": ("T. Nagar Centre",),
    "Pune": ("Hinjewadi Centre",),
    "Kolkata": ("Salt Lake Centre",),
}

_ALIASES: dict[str, str] = {
    "bangalore": "Bengaluru",
    "bombay": "Mumbai",
    "new delhi": "Delhi",
    "delhi ncr": "Delhi",
    "madras": "Chennai",
    "calcutta": "Kolkata",
    "बेंगलुरु": "Bengaluru",
    "बैंगलोर": "Bengaluru",
    "हैदराबाद": "Hyderabad",
    "मुंबई": "Mumbai",
    "दिल्ली": "Delhi",
    "चेन्नई": "Chennai",
    "पुणे": "Pune",
    "कोलकाता": "Kolkata",
}

_LOOKUP: dict[str, str] = {**{city.casefold(): city for city in CENTRES}, **_ALIASES}


def canonical_city(raw: str | None) -> str | None:
    """Maps a spoken or typed city to a served city, or None when unserved."""
    if not raw:
        return None
    return _LOOKUP.get(" ".join(raw.casefold().split()))
