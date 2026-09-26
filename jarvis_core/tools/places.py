"""Maps, addresses, and nearby food/shops via OpenStreetMap (no API key)."""
from __future__ import annotations

import webbrowser
from urllib.parse import quote

import requests

from . import tool

UA = {"User-Agent": "Jarvis-local-assistant/1.0 (personal desktop; nominatim)"}
NOMINATIM = "https://nominatim.openstreetmap.org/search"
OVERPASS = "https://overpass-api.de/api/interpreter"


def _ip_location() -> tuple[float, float, str]:
    attempts = [
        ("https://ipapi.co/json/", lambda d: (
            float(d["latitude"]), float(d["longitude"]),
            ", ".join(p for p in (d.get("city"), d.get("region"), d.get("country_name")) if p))),
        ("http://ip-api.com/json/", lambda d: (
            float(d["lat"]), float(d["lon"]),
            ", ".join(p for p in (d.get("city"), d.get("regionName"), d.get("country")) if p))),
        ("https://ipinfo.io/json", lambda d: (
            float(d["loc"].split(",")[0]), float(d["loc"].split(",")[1]),
            ", ".join(p for p in (d.get("city"), d.get("region"), d.get("country")) if p))),
    ]
    last = None
    for url, parse in attempts:
        try:
            d = requests.get(url, headers=UA, timeout=8).json()
            lat, lon, label = parse(d)
            if lat and lon:
                return lat, lon, label or "your area"
        except Exception as e:
            last = e
    raise RuntimeError(last or "IP geolocation failed")


def _here(ctx) -> tuple[float, float, str]:
    city = (ctx.cfg.get("weather.default_city") or ctx.cfg.get("location.default_area") or "").strip()
    if city:
        hits = _geocode(city, 1)
        if hits:
            h = hits[0]
            return h["lat"], h["lon"], h["label"]
    return _ip_location()


def _geocode(query: str, limit: int = 5, near: tuple[float, float] | None = None) -> list[dict]:
    params = {"q": query, "format": "json", "addressdetails": 1, "limit": limit}
    if near:
        lat, lon = near
        delta = 0.12
        params["viewbox"] = f"{lon - delta},{lat + delta},{lon + delta},{lat - delta}"
        params["bounded"] = 1
    r = requests.get(NOMINATIM, params=params, headers=UA, timeout=12)
    r.raise_for_status()
    out = []
    for item in r.json() or []:
        out.append({
            "label": item.get("display_name", query),
            "lat": float(item["lat"]),
            "lon": float(item["lon"]),
            "type": item.get("type") or item.get("class") or "",
        })
    return out


def _km(a_lat, a_lon, b_lat, b_lon) -> float:
    from math import cos, radians, sqrt
    x = (b_lon - a_lon) * cos(radians((a_lat + b_lat) / 2))
    y = b_lat - a_lat
    return sqrt(x * x + y * y) * 111.32


def _maps_url(query: str = "", lat: float | None = None, lon: float | None = None) -> str:
    if lat is not None and lon is not None and not query:
        return f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
    return f"https://www.google.com/maps/search/?api=1&query={quote(query)}"


def _overpass_nearby(lat: float, lon: float, kind: str, radius_m: int = 3500) -> list[dict]:
    kind = (kind or "food").lower()
    if any(w in kind for w in ("shop", "buy", "store", "supermarket", "grocery", "market")):
        filters = 'nwr["shop"~"supermarket|convenience|greengrocer|bakery|butcher|mall"]'
    elif any(w in kind for w in ("cafe", "coffee", "tea")):
        filters = 'nwr["amenity"~"cafe|coffee_shop"]'
    elif any(w in kind for w in ("bar", "drink", "pub")):
        filters = 'nwr["amenity"~"bar|pub|biergarten"]'
    else:
        filters = 'nwr["amenity"~"restaurant|fast_food|cafe|food_court"]'
    cuisine = ""
    for word in ("pizza", "sushi", "burger", "taco", "indian", "chinese", "thai", "italian",
                 "mexican", "kebab", "ramen", "seafood", "vegan", "vegetarian", "bbq",
                 "grill", "chicken", "fish", "pasta", "sandwich"):
        if word in kind:
            cuisine = word
            break
    extra = f'nwr["cuisine"~"{cuisine}"]' if cuisine else ""
    q = f"""[out:json][timeout:18];
(
  {filters}(around:{radius_m},{lat},{lon});
  {extra}(around:{radius_m},{lat},{lon});
);
out center 20;"""
    r = requests.post(OVERPASS, data={"data": q}, headers=UA, timeout=10)
    r.raise_for_status()
    places = []
    seen = set()
    for el in (r.json() or {}).get("elements", []):
        tags = el.get("tags") or {}
        name = tags.get("name")
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        c = el.get("center") or {}
        plat = el.get("lat") or c.get("lat")
        plon = el.get("lon") or c.get("lon")
        street = " ".join(x for x in (tags.get("addr:housenumber"), tags.get("addr:street")) if x)
        city = tags.get("addr:city") or tags.get("addr:suburb") or ""
        addr = ", ".join(p for p in (street, city) if p)
        kind_tag = tags.get("amenity") or tags.get("shop") or tags.get("cuisine") or ""
        places.append({"name": name, "address": addr, "kind": kind_tag, "lat": plat, "lon": plon})
        if len(places) >= 8:
            break
    return places


@tool("lookup_address",
      "Look up a place or street address and optionally open it on Google Maps.",
      {"query": "place name or address", "open_map": "true/false, default true"})
def lookup_address(ctx, query: str, open_map: bool = True):
    query = (query or "").strip()
    if not query:
        return f"What should I look up on the map, {ctx.name}?"
    try:
        hits = _geocode(query, 3)
    except Exception as e:
        return f"Maps lookup failed ({e}). Check the internet connection, {ctx.name}."
    if not hits:
        return f"I couldn't find '{query}' on the map, {ctx.name}."
    best = hits[0]
    if str(open_map).lower() not in ("false", "0", "no"):
        webbrowser.open(_maps_url(best["label"], best["lat"], best["lon"]))
    others = "; ".join(h["label"] for h in hits[1:3])
    extra = f" Other matches: {others}." if others else ""
    return (f"{best['label']}. I've opened it on Google Maps, {ctx.name}."
            if str(open_map).lower() not in ("false", "0", "no")
            else f"{best['label']}.{extra}")


@tool("open_maps", "Open Google Maps for a query, address, or current area.",
      {"query": "place, address, or empty for current area"})
def open_maps(ctx, query: str = ""):
    query = (query or "").strip()
    if not query:
        try:
            lat, lon, label = _here(ctx)
            webbrowser.open(_maps_url(lat=lat, lon=lon))
            return f"Opening maps around {label}, {ctx.name}."
        except Exception as e:
            webbrowser.open("https://maps.google.com")
            return f"Opened Google Maps, {ctx.name}. I couldn't pin your area ({e})."
    try:
        hits = _geocode(query, 1)
        if hits:
            webbrowser.open(_maps_url(hits[0]["label"], hits[0]["lat"], hits[0]["lon"]))
            return f"Opening {hits[0]['label']} on Google Maps, {ctx.name}."
    except Exception:
        pass
    webbrowser.open(_maps_url(query))
    return f"Searching Google Maps for {query}, {ctx.name}."


@tool("find_places",
      "Find nearby restaurants, cafes, or shops. Use for food advice and where to get something.",
      {"query": "what to find, e.g. sushi, pharmacy, supermarket", "area": "city or neighbourhood, optional"})
def find_places(ctx, query: str, area: str = ""):
    query = (query or "food").strip()
    area = (area or "").strip()
    try:
        if area:
            hits = _geocode(area, 1)
            if not hits:
                return f"I couldn't locate '{area}', {ctx.name}."
            lat, lon, label = hits[0]["lat"], hits[0]["lon"], hits[0]["label"]
        else:
            lat, lon, label = _here(ctx)
    except Exception as e:
        return f"I couldn't determine your area ({e}), {ctx.name}."

    city = label.split(",")[0]
    places: list[dict] = []
    try:
        searches = [f"{query} {city}", f"{query} restaurant {city}", f"{query} near {city}"]
        seen = set()
        for q in searches:
            for item in _geocode(q, 6):
                key = item["label"][:80]
                if key in seen:
                    continue
                if _km(lat, lon, item["lat"], item["lon"]) > 18:
                    continue
                seen.add(key)
                places.append({
                    "name": item["label"].split(",")[0],
                    "address": item["label"],
                    "kind": item.get("type") or "",
                    "lat": item["lat"],
                    "lon": item["lon"],
                })
            if len(places) >= 6:
                break
    except Exception:
        pass
    try:
        extra = _overpass_nearby(lat, lon, query)
        have = {p["name"].lower() for p in places}
        for p in extra:
            if p["name"].lower() not in have:
                places.append(p)
    except Exception:
        pass
    if not places:
        try:
            from .web import _ddg
            web = _ddg(f"best {query} near {city}", 5)
            webbrowser.open(_maps_url(f"{query} near {city}"))
            if web:
                listing = " ".join(f"{r['title']}: {r['snippet']}" for r in web[:4])
                return (f"Around {city}: {listing} I've also opened Google Maps for {query}, {ctx.name}.")
        except Exception as e:
            return f"I couldn't search nearby places ({e}), {ctx.name}."
        return f"Nothing obvious nearby for '{query}' around {city}, {ctx.name}."
    webbrowser.open(_maps_url(f"{query} near {city}"))
    spoken = "; ".join(
        (f"{p['name']} ({p['address'].split(',')[1].strip()})" if "," in p.get("address", "")
         else p["name"])
        for p in places[:4]
    )
    return (f"Near {city} I found: {spoken}. "
            f"I've opened the area on Google Maps, {ctx.name}.")
