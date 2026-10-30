"""Illustrative fixture adapter. Everything it returns is synthetic demo data, never live Qloo output."""
from __future__ import annotations

import hashlib
from typing import Any, Optional

_POOL = {
    "urn:entity:brand": [
        ("Sample Studio Coffee", ["Design-led", "Minimal", "Ritual"]),
        ("Sample Everyday Tea", ["Routine", "Wellness", "Comfort"]),
        ("Sample Trail Outfitters", ["Outdoor", "Community", "Durable"]),
        ("Sample Vinyl Club", ["Music", "Collector", "Expressive"]),
        ("Sample Farm Table", ["Food-led", "Social", "Seasonal"]),
        ("Sample Pause Water", ["Calm", "Routine", "Clean"]),
    ],
    "urn:entity:artist": [
        ("Sample Lo-fi Collective", ["Chill", "Creative", "Intimate"]),
        ("Sample Folk Trio", ["Acoustic", "Community", "Warm"]),
        ("Sample Synth Duo", ["Expressive", "Electronic", "Night"]),
        ("Sample Jazz Quartet", ["Sophisticated", "Improvised", "Smooth"]),
    ],
    "urn:entity:tv_show": [
        ("Sample Kitchen Stories", ["Food culture", "Social", "Warm"]),
        ("Sample Design Files", ["Aesthetic", "Creative process", "Slow"]),
        ("Sample Trail Diaries", ["Outdoor", "Adventure", "Community"]),
    ],
    "urn:entity:place": [
        ("Sample Rooftop Cafe", ["Coffee", "Social", "Urban"]),
        ("Sample Gallery Bar", ["Art", "Cocktails", "Design-led"]),
        ("Sample Garden Eatery", ["Outdoor seating", "Food-led", "Casual"]),
        ("Sample Record Cafe", ["Music", "Coffee", "Creative"]),
    ],
}


def _h(s: str) -> int:
    return int(hashlib.sha1(s.encode()).hexdigest(), 16)


class FixtureQlooAdapter:
    mode = "fixture"

    async def search_entities(self, query: str, types: Optional[str] = None, take: int = 5) -> list[dict]:
        return [
            {
                "entity_id": f"FIXTURE-ENT-{_h(query) % 10**6}",
                "name": f"{query} (illustrative)",
                "type": types or "urn:entity:brand",
                "description": "Illustrative demo data, not live Qloo.",
                "popularity": 0.5,
                "disambiguation": None,
            }
        ]

    async def search_tags(self, query: str, take: int = 5) -> list[dict]:
        return [
            {
                "id": f"urn:tag:fixture:{query.lower().replace(' ', '_')}",
                "name": query.title(),
                "type": "urn:tag:fixture",
                "parents": [],
                "popularity": 0.5,
            }
        ]

    async def insights(self, params: dict[str, Any]) -> list[dict]:
        ftype = params.get("filter.type", "urn:entity:brand")
        pool = _POOL.get(ftype, _POOL["urn:entity:brand"])
        seed = _h(str(params.get("signal.interests.entities", "")) + str(params.get("signal.interests.tags", "")) + str(params.get("filter.location.query", "")))
        out = []
        for i in range(min(int(params.get("take", 6)), len(pool))):
            name, tags = pool[(seed + i) % len(pool)]
            out.append(
                {
                    "entity_id": f"FIXTURE-{_h(name) % 10**6}",
                    "name": name,
                    "type": ftype,
                    "affinity": round(0.9 - i * 0.07, 3),
                    "popularity": 0.5,
                    "tags": tags,
                    "description": "Illustrative demo data, not live Qloo.",
                    "explained_by": [],
                }
            )
        return out
