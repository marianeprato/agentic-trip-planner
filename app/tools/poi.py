"""Points-of-interest search tool backed by a small deterministic in-repo dataset.

A real POI API (e.g. OpenTripMap/Geoapify) needs an API key and has flaky
free tiers -- tangential to the SDK concepts this project exercises. This
mock keeps results deterministic for testing while still requiring the
agent to filter/reason over structured data.
"""

from __future__ import annotations

from agents import function_tool

from app.models import PointOfInterest

_POI_DATASET: dict[str, list[PointOfInterest]] = {
    "paris": [
        PointOfInterest(name="Louvre Museum", category="museum", description="World-famous art museum, home to the Mona Lisa.", indoor=True, estimated_cost=22.0, currency="EUR"),
        PointOfInterest(name="Eiffel Tower", category="landmark", description="Iconic iron lattice tower with city-wide views.", indoor=False, estimated_cost=29.0, currency="EUR"),
        PointOfInterest(name="Le Marais", category="neighborhood", description="Historic district with cafes, boutiques, and galleries.", indoor=False, estimated_cost=0.0, currency="EUR"),
        PointOfInterest(name="Musée d'Orsay", category="museum", description="Impressionist and post-impressionist masterpieces in a former railway station.", indoor=True, estimated_cost=16.0, currency="EUR"),
    ],
    "tokyo": [
        PointOfInterest(name="Senso-ji Temple", category="landmark", description="Tokyo's oldest Buddhist temple in Asakusa.", indoor=False, estimated_cost=0.0, currency="JPY"),
        PointOfInterest(name="teamLab Planets", category="museum", description="Immersive digital art installations.", indoor=True, estimated_cost=3800.0, currency="JPY"),
        PointOfInterest(name="Tsukiji Outer Market", category="food", description="Street food and fresh seafood stalls.", indoor=False, estimated_cost=2000.0, currency="JPY"),
        PointOfInterest(name="Shinjuku Gyoen", category="park", description="Spacious park blending Japanese, French, and English garden styles.", indoor=False, estimated_cost=500.0, currency="JPY"),
    ],
    "new york": [
        PointOfInterest(name="Metropolitan Museum of Art", category="museum", description="One of the world's largest and most comprehensive art museums.", indoor=True, estimated_cost=30.0, currency="USD"),
        PointOfInterest(name="Central Park", category="park", description="843-acre park in the middle of Manhattan.", indoor=False, estimated_cost=0.0, currency="USD"),
        PointOfInterest(name="High Line", category="landmark", description="Elevated linear park built on a former rail line.", indoor=False, estimated_cost=0.0, currency="USD"),
        PointOfInterest(name="Chelsea Market", category="food", description="Indoor food hall with dozens of vendors.", indoor=True, estimated_cost=15.0, currency="USD"),
    ],
    "rome": [
        PointOfInterest(name="Colosseum", category="landmark", description="Ancient Roman amphitheater.", indoor=False, estimated_cost=18.0, currency="EUR"),
        PointOfInterest(name="Vatican Museums", category="museum", description="Includes the Sistine Chapel.", indoor=True, estimated_cost=20.0, currency="EUR"),
        PointOfInterest(name="Trastevere", category="neighborhood", description="Cobblestoned district known for trattorias and nightlife.", indoor=False, estimated_cost=0.0, currency="EUR"),
    ],
    "lisbon": [
        PointOfInterest(name="Belém Tower", category="landmark", description="16th-century fortified tower on the Tagus estuary.", indoor=False, estimated_cost=6.0, currency="EUR"),
        PointOfInterest(name="LX Factory", category="neighborhood", description="Creative hub with shops, cafes, and street art.", indoor=False, estimated_cost=0.0, currency="EUR"),
        PointOfInterest(name="Time Out Market", category="food", description="Food hall featuring the city's top chefs.", indoor=True, estimated_cost=12.0, currency="EUR"),
    ],
}

_GENERIC_FALLBACK_TEMPLATE: list[tuple[str, str, str, bool, float]] = [
    ("City Walking Tour", "landmark", "Self-guided or group walking tour of the historic center.", False, 0.0),
    ("Local History Museum", "museum", "Museum covering the city's history and culture.", True, 12.0),
    ("Central Market", "food", "Local market with regional food and produce.", True, 10.0),
    ("Main Park", "park", "The city's largest public park, popular with locals.", False, 0.0),
]


@function_tool
def search_points_of_interest(destination: str, category: str | None = None) -> list[PointOfInterest]:
    """Search for points of interest in a destination, optionally filtered by category.

    Args:
        destination: City or place name, e.g. "Paris" or "Tokyo".
        category: Optional filter, e.g. "museum", "food", "park", "landmark", "neighborhood".
    """
    key = destination.strip().lower()
    if key in _POI_DATASET:
        results = _POI_DATASET[key]
    else:
        results = [
            PointOfInterest(
                name=f"{name} ({destination})",
                category=cat,
                description=description,
                indoor=indoor,
                estimated_cost=cost,
                currency="USD",
            )
            for name, cat, description, indoor, cost in _GENERIC_FALLBACK_TEMPLATE
        ]

    if category:
        results = [poi for poi in results if poi.category.lower() == category.lower()]
    return results
