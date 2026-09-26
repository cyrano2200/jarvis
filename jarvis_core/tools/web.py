"""Web search + summarise, page reading and weather (no API keys needed)."""
from __future__ import annotations

import html
import re
from urllib.parse import parse_qs, quote, unquote, urlparse

import requests

from . import tool

UA = {"User-Agent": "Mozilla/5.0 (Jarvis local assistant)"}


def _ddg(query: str, n: int = 5) -> list[dict]:
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        with DDGS() as d:
            res = list(d.text(query, max_results=n))
        out = [{"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")}
               for r in res]
        if out:
            return out
    except Exception:
        pass
    # HTML fallback
    r = requests.post("https://html.duckduckgo.com/html/", data={"q": query}, headers=UA, timeout=12)
    out = []
    for m in re.finditer(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?'
                         r'class="result__snippet"[^>]*>(.*?)</a>', r.text, re.S):
        url = m.group(1)
        if "uddg=" in url:
            url = unquote(parse_qs(urlparse(url).query).get("uddg", [url])[0])
        strip = lambda s: html.unescape(re.sub(r"<.*?>", "", s)).strip()
        out.append({"title": strip(m.group(2)), "url": url, "snippet": strip(m.group(3))})
        if len(out) >= n:
            break
    return out


def fetch_text(url: str, limit: int = 6000) -> str:
    r = requests.get(url, headers=UA, timeout=12)
    r.raise_for_status()
    if "text" not in r.headers.get("content-type", "text"):
        return ""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, "html.parser")
        for t in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
            t.decompose()
        text = soup.get_text(" ", strip=True)
    except ImportError:
        text = html.unescape(re.sub(r"<(script|style).*?</\1>|<.*?>", " ", r.text, flags=re.S))
    return re.sub(r"\s+", " ", text)[:limit]


@tool("web_search", "Search the web and (optionally) summarise the top results.",
      {"query": "search query", "summarize": "true/false, default true"})
def web_search(ctx, query: str, summarize: bool = True):
    results = _ddg(query, 5)
    if not results:
        return f"The search returned nothing, {ctx.name}. Possibly offline."
    listing = " | ".join(f"{r['title']}: {r['snippet']}" for r in results[:4])
    if str(summarize).lower() in ("false", "0", "no") or not ctx.brain.available():
        return listing
    pages = []
    for r in results[:3]:
        try:
            pages.append(f"SOURCE {r['url']}\n{fetch_text(r['url'], 3500)}")
        except Exception:
            pages.append(f"SOURCE {r['url']}\n{r['snippet']}")
    try:
        summary = ctx.brain.summarize("\n\n".join(pages),
                                      f"Summarise what these sources say about: {query}")
        return f"{summary} (Sources: {', '.join(urlparse(r['url']).netloc for r in results[:3])})"
    except Exception:
        return listing


@tool("read_webpage", "Fetch a web page and return its readable text.", {"url": "page URL"})
def read_webpage(ctx, url: str):
    try:
        return fetch_text(url, 5000) or "That page has no readable text."
    except Exception as e:
        return f"Couldn't read that page: {e}"


WMO = {0: "clear skies", 1: "mostly clear", 2: "partly cloudy", 3: "overcast", 45: "foggy", 48: "foggy",
       51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 61: "light rain", 63: "rain",
       65: "heavy rain", 71: "light snow", 73: "snow", 75: "heavy snow", 80: "rain showers",
       81: "rain showers", 82: "violent showers", 95: "thunderstorms", 96: "thunderstorms with hail",
       99: "thunderstorms with hail"}


@tool("weather", "Current weather and today's outlook for a city (defaults to configured/IP location).",
      {"city": "city name, optional"})
def weather(ctx, city: str = ""):
    city = (city or ctx.cfg.get("weather.default_city") or "").strip()
    imperial = ctx.cfg.get("weather.units") == "imperial"
    if city:
        g = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                         params={"name": city, "count": 1}, timeout=10).json()
        if not g.get("results"):
            return f"I couldn't locate '{city}' on the map, {ctx.name}."
        loc = g["results"][0]
        lat, lon, label = loc["latitude"], loc["longitude"], loc["name"]
    else:
        loc = {}
        for url in ("https://ipapi.co/json/", "http://ip-api.com/json/", "https://ipinfo.io/json"):
            try:
                loc = requests.get(url, headers=UA, timeout=8).json()
                if loc.get("latitude") or loc.get("lat") or loc.get("loc"):
                    break
            except Exception:
                continue
        if loc.get("loc"):
            lat_s, lon_s = loc["loc"].split(",")
            lat, lon, label = float(lat_s), float(lon_s), loc.get("city", "your location")
        else:
            lat = float(loc.get("latitude") or loc["lat"])
            lon = float(loc.get("longitude") or loc["lon"])
            label = loc.get("city") or loc.get("city", "your location")
    f = requests.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": lat, "longitude": lon, "timezone": "auto",
        "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "temperature_unit": "fahrenheit" if imperial else "celsius",
        "wind_speed_unit": "mph" if imperial else "kmh"}, timeout=10).json()
    c, d = f["current"], f["daily"]
    u = "F" if imperial else "C"
    rain = d["precipitation_probability_max"][0]
    return (f"In {label} it's {c['temperature_2m']:.0f} degrees {u} with {WMO.get(c['weather_code'], 'mixed conditions')}, "
            f"feels like {c['apparent_temperature']:.0f}. Today's range is {d['temperature_2m_min'][0]:.0f} "
            f"to {d['temperature_2m_max'][0]:.0f}, with a {rain} percent chance of rain, {ctx.name}.")
