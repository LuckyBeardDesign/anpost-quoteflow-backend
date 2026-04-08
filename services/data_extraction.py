"""
Data Extraction Service
Deep scraping using Playwright for extracting structured data from URLs
Supports ScraperAPI for sites with bot detection
"""

import asyncio
import os
import re
import httpx
from typing import Optional
from pydantic import BaseModel

from .link_preview import detect_content_type
from .extractors import extract_car_data, extract_property_data, extract_travel_data

# ScraperAPI configuration
SCRAPER_API_KEY = os.getenv("SCRAPER_API_KEY")
SCRAPER_API_URL = "http://api.scraperapi.com"

# Domains that require premium ScraperAPI (need upgraded plan)
PREMIUM_DOMAINS = [
    "mobile.de",
    "suchen.mobile.de",
    "autoscout24.de",
    "autoscout24.com",
]


async def _fetch_seo_metadata(url: str) -> dict:
    """
    Fetch SEO metadata (title, description, OG tags) via simple HTTP.
    Works even on sites that block Playwright/scraping.
    Returns dict with title, description, og_title, og_description.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "max-age=0",
        "Sec-Ch-Ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"macOS"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers, follow_redirects=True)
            if response.status_code != 200:
                return {}

            html = response.text
            result = {}

            # Extract title
            title_match = re.search(r'<title[^>]*>([^<]+)</title>', html, re.I)
            if title_match:
                result["title"] = title_match.group(1).strip()

            # Extract meta description
            desc_match = re.search(r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']+)["\']', html, re.I)
            if not desc_match:
                desc_match = re.search(r'<meta[^>]*content=["\']([^"\']+)["\'][^>]*name=["\']description["\']', html, re.I)
            if desc_match:
                result["description"] = desc_match.group(1).strip()

            # Extract og:title
            og_title = re.search(r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\']([^"\']+)["\']', html, re.I)
            if not og_title:
                og_title = re.search(r'<meta[^>]*content=["\']([^"\']+)["\'][^>]*property=["\']og:title["\']', html, re.I)
            if og_title:
                result["og_title"] = og_title.group(1).strip()

            # Extract og:description
            og_desc = re.search(r'<meta[^>]*property=["\']og:description["\'][^>]*content=["\']([^"\']+)["\']', html, re.I)
            if not og_desc:
                og_desc = re.search(r'<meta[^>]*content=["\']([^"\']+)["\'][^>]*property=["\']og:description["\']', html, re.I)
            if og_desc:
                result["og_description"] = og_desc.group(1).strip()

            return result
    except Exception:
        return {}


def _parse_car_from_seo(seo_data: dict) -> dict:
    """
    Parse car make, model, year, price from SEO metadata.
    Works with German car listing sites like mobile.de.
    """
    from .extractors.car import _parse_car_title

    structured = {}

    # Combine title and description for parsing
    title = seo_data.get("og_title") or seo_data.get("title") or ""
    description = seo_data.get("og_description") or seo_data.get("description") or ""

    if not title:
        return structured

    # Parse make and model from title (e.g., "BMW X5 M für 149.880 €")
    make, model = _parse_car_title(title)
    if make:
        structured["make"] = make
    if model:
        structured["model"] = model

    # Extract price from title (e.g., "für 149.880 €" or "149.880 €")
    price_match = re.search(r'(\d{1,3}(?:[.,]\d{3})*)\s*€', title)
    if price_match:
        price_str = price_match.group(1).replace(".", "").replace(",", "")
        try:
            price = int(price_str)
            if 500 < price < 5000000:
                structured["price"] = price
                structured["currency"] = "EUR"
        except ValueError:
            pass

    # Parse description for additional details
    # e.g., "Neufahrzeug, Unfallfrei • 0 km • 460 kW (625 PS) • Benzin • Automatik"
    if description:
        # Mileage
        mileage_match = re.search(r'(\d{1,3}(?:[.,]?\d{3})*)\s*km\b', description, re.I)
        if mileage_match:
            mileage_str = mileage_match.group(1).replace(".", "").replace(",", "")
            try:
                structured["mileage"] = int(mileage_str)
                structured["mileageUnit"] = "km"
            except ValueError:
                pass

        # Power in kW or PS
        power_match = re.search(r'(\d+)\s*kW', description, re.I)
        if power_match:
            structured["power"] = int(power_match.group(1))
            structured["powerUnit"] = "kW"
        else:
            ps_match = re.search(r'(\d+)\s*PS', description, re.I)
            if ps_match:
                structured["power"] = int(ps_match.group(1))
                structured["powerUnit"] = "hp"

        # Fuel type
        fuel_types = {
            "benzin": "petrol",
            "diesel": "diesel",
            "elektro": "electric",
            "hybrid": "hybrid",
            "plug-in": "hybrid",
            "erdgas": "gas",
            "autogas": "lpg",
        }
        desc_lower = description.lower()
        for german, english in fuel_types.items():
            if german in desc_lower:
                structured["fuelType"] = english
                break

        # Transmission
        if "automatik" in desc_lower or "automatic" in desc_lower:
            structured["transmission"] = "automatic"
        elif "schaltgetriebe" in desc_lower or "manuell" in desc_lower or "manual" in desc_lower:
            structured["transmission"] = "manual"

        # Year from description or check if "Neufahrzeug"
        year_match = re.search(r'\b(20[0-2]\d|19[89]\d)\b', description)
        if year_match:
            structured["year"] = int(year_match.group(1))
        elif "neufahrzeug" in desc_lower or "neuwagen" in desc_lower:
            import datetime
            structured["year"] = datetime.datetime.now().year

    return structured


class ExtractionResult(BaseModel):
    url: str
    contentType: str
    structured: dict
    rawText: str
    confidence: float
    error: Optional[str] = None


# Lazy load playwright to avoid startup overhead
_playwright = None
_browser = None


async def get_browser():
    """Get or create a Playwright browser instance."""
    global _playwright, _browser

    if _browser is None:
        from playwright.async_api import async_playwright
        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--window-size=1920,1080",
                "--start-maximized",
            ]
        )

    return _browser


async def close_browser():
    """Close the Playwright browser instance."""
    global _playwright, _browser

    if _browser:
        await _browser.close()
        _browser = None
    if _playwright:
        await _playwright.stop()
        _playwright = None


def _can_use_scraper_api() -> bool:
    """Check if ScraperAPI is available as a fallback."""
    return bool(SCRAPER_API_KEY)


def _needs_premium_proxy(url: str) -> bool:
    """Check if URL requires premium ScraperAPI proxy."""
    from urllib.parse import urlparse
    domain = urlparse(url).netloc.lower()
    return any(premium in domain for premium in PREMIUM_DOMAINS)


async def _fetch_via_scraper_api(url: str) -> tuple[str, str]:
    """
    Fetch page content via ScraperAPI.
    Returns (html, raw_text) tuple.
    """
    params = {
        "api_key": SCRAPER_API_KEY,
        "url": url,
        "render": "true",  # Enable JavaScript rendering
        "device_type": "desktop",
    }

    # Add premium for protected domains
    # Note: Some sites (mobile.de, autoscout24) require enterprise plans
    if _needs_premium_proxy(url):
        params["premium"] = "true"

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(SCRAPER_API_URL, params=params)
        response.raise_for_status()
        html = response.text

        # Extract text from HTML
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")

        # Remove script and style elements
        for element in soup(["script", "style", "noscript"]):
            element.decompose()

        raw_text = soup.get_text(separator=" ", strip=True)

        return html, raw_text


async def extract_data(url: str) -> ExtractionResult:
    """
    Extract structured data from a URL.
    1. First tries Playwright
    2. Falls back to ScraperAPI if blocked or low confidence
    Returns the extracted data with content type detection.
    """
    content_type = detect_content_type(url)
    used_scraper_api = False

    try:
        # First attempt: Use Playwright
        html, raw_text = await _fetch_via_playwright(url)

        # Check if we got blocked
        blocked_indicators = [
            "zugriff verweigert", "access denied", "captcha",
            "blocked", "forbidden", "robot", "bot detected",
            "please verify", "checking your browser", "powered and protected",
        ]
        raw_text_lower = raw_text.lower()[:2000]
        is_blocked = any(indicator in raw_text_lower for indicator in blocked_indicators)

        # Extract data from Playwright result
        structured, confidence = _extract_structured_data(html, url, content_type)

        # Check if extracted data looks like blocked page garbage
        # e.g., make="Zugriff", model="verweigert" from "Zugriff verweigert" page
        garbage_indicators = ["zugriff", "verweigert", "denied", "access", "blocked", "forbidden", "captcha"]
        make_lower = str(structured.get("make", "")).lower()
        model_lower = str(structured.get("model", "")).lower()
        if any(ind in make_lower or ind in model_lower for ind in garbage_indicators):
            is_blocked = True
            structured = {}
            confidence = 0.0

        # Fallback to ScraperAPI if blocked or very low confidence
        if (is_blocked or confidence < 0.2) and _can_use_scraper_api():
            try:
                html, raw_text = await _fetch_via_scraper_api(url)
                structured, confidence = _extract_structured_data(html, url, content_type)
                used_scraper_api = True
                is_blocked = False  # ScraperAPI succeeded
            except Exception as scraper_error:
                # ScraperAPI failed, continue with original Playwright result
                pass

        # If still blocked after all attempts, try SEO metadata fallback
        # This works for sites like mobile.de that block scraping but serve SEO tags
        if is_blocked and confidence < 0.3:
            seo_data = await _fetch_seo_metadata(url)
            if seo_data and (seo_data.get("title") or seo_data.get("og_title")):
                # Parse car data from SEO metadata
                if content_type == "car_listing" or detect_content_type(url) == "car_listing":
                    seo_structured = _parse_car_from_seo(seo_data)
                    if seo_structured:
                        structured = seo_structured
                        confidence = _calculate_car_confidence(structured)
                        raw_text = f"[Extracted from SEO] {seo_data.get('title', '')} - {seo_data.get('description', '')}"

                        return ExtractionResult(
                            url=url,
                            contentType="car_listing",
                            structured=structured,
                            rawText=raw_text[:10000] if len(raw_text) > 10000 else raw_text,
                            confidence=confidence,
                            error=None,  # SEO extraction worked!
                        )

            # Final fallback: link preview
            from .link_preview import fetch_link_preview
            preview = await fetch_link_preview(url)
            preview_blocked_terms = ["unable to load", "denied", "error", "blocked", "forbidden"]
            preview_title_lower = (preview.title or "").lower()
            preview_valid = preview.title and not any(term in preview_title_lower for term in preview_blocked_terms)

            if preview_valid:
                fallback_data = _parse_preview_fallback(preview, content_type)
                if fallback_data:
                    structured.update(fallback_data)
                    confidence = _calculate_car_confidence(structured) if content_type == "car_listing" else 0.3
                    raw_text = f"[Extracted from preview] {preview.title or ''} - {preview.description or ''}"
            else:
                structured = {}
                confidence = 0.0
                raw_text = ""

            return ExtractionResult(
                url=url,
                contentType=content_type,
                structured=structured,
                rawText=raw_text[:10000] if len(raw_text) > 10000 else raw_text,
                confidence=confidence,
                error="Site blocked deep extraction - using preview data",
            )

        # Truncate raw text if too long
        if len(raw_text) > 10000:
            raw_text = raw_text[:10000] + "..."

        return ExtractionResult(
            url=url,
            contentType=content_type,
            structured=structured,
            rawText=raw_text,
            confidence=confidence,
            error=None,
        )

    except Exception as e:
        return ExtractionResult(
            url=url,
            contentType=content_type,
            structured={},
            rawText="",
            confidence=0.0,
            error=str(e),
        )


def _extract_structured_data(html: str, url: str, content_type: str) -> tuple[dict, float]:
    """Extract structured data from HTML and return (data, confidence)."""
    structured = {}
    confidence = 0.0

    if content_type == "car_listing":
        structured = extract_car_data(html, url)
        confidence = _calculate_car_confidence(structured)
    elif content_type == "property_listing":
        structured = extract_property_data(html, url)
        confidence = _calculate_property_confidence(structured)
    elif content_type == "travel_listing":
        structured = extract_travel_data(html, url)
        confidence = _calculate_travel_confidence(structured)
    else:
        # Try all extractors and use the one with highest confidence
        car_data = extract_car_data(html, url)
        car_conf = _calculate_car_confidence(car_data)

        property_data = extract_property_data(html, url)
        property_conf = _calculate_property_confidence(property_data)

        travel_data = extract_travel_data(html, url)
        travel_conf = _calculate_travel_confidence(travel_data)

        if car_conf >= property_conf and car_conf >= travel_conf and car_conf > 0.2:
            structured = car_data
            confidence = car_conf
        elif property_conf >= travel_conf and property_conf > 0.2:
            structured = property_data
            confidence = property_conf
        elif travel_conf > 0.2:
            structured = travel_data
            confidence = travel_conf
        else:
            confidence = 0.1

    return structured, confidence


async def _fetch_via_playwright(url: str) -> tuple[str, str]:
    """
    Fetch page content via Playwright.
    Returns (html, raw_text) tuple.
    """
    browser = await get_browser()
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        viewport={"width": 1920, "height": 1080},
        locale="de-DE",
        timezone_id="Europe/Berlin",
        geolocation={"latitude": 52.52, "longitude": 13.405},
        permissions=["geolocation"],
        java_script_enabled=True,
        bypass_csp=True,
        extra_http_headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Sec-Ch-Ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"macOS"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        },
    )

    page = await context.new_page()

    # Hide webdriver detection
    await page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        Object.defineProperty(navigator, 'languages', { get: () => ['de-DE', 'de', 'en-US', 'en'] });
        window.chrome = { runtime: {} };
    """)

    # Navigate with timeout
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
    except Exception:
        # Fallback to domcontentloaded if networkidle times out
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)

    # Wait a bit for dynamic content
    await asyncio.sleep(1)

    # Handle cookie consent banners
    await _handle_cookie_consent(page)

    # Get the full page HTML
    html = await page.content()

    # Get visible text
    raw_text = await page.evaluate("""
        () => {
            const clone = document.body.cloneNode(true);
            // Remove script and style elements
            clone.querySelectorAll('script, style, noscript').forEach(el => el.remove());
            return clone.innerText;
        }
    """)

    await context.close()

    return html, raw_text


def _parse_preview_fallback(preview, content_type: str) -> dict:
    """Parse basic car info from link preview title/description."""
    import re

    data = {}
    text = f"{preview.title or ''} {preview.description or ''}"

    if content_type != "car_listing" or not text.strip():
        return data

    # Import the car extractor helpers
    from .extractors.car import _parse_car_title

    # Try to extract make/model from title
    if preview.title:
        make, model = _parse_car_title(preview.title)
        if make:
            data["make"] = make
        if model:
            data["model"] = model

    # Try to find year
    year_match = re.search(r"\b(19[89]\d|20[0-2]\d)\b", text)
    if year_match:
        data["year"] = int(year_match.group(1))

    # Try to find price
    price_match = re.search(r"[€]\s*(\d{1,3}[.,]?\d{3})", text)
    if price_match:
        price_str = price_match.group(1).replace(".", "").replace(",", "")
        try:
            price = int(price_str)
            if 500 < price < 2000000:
                data["price"] = price
        except ValueError:
            pass

    # Try to find mileage
    mileage_match = re.search(r"(\d{1,3}[.,]?\d{3})\s*km", text, re.I)
    if mileage_match:
        mileage_str = mileage_match.group(1).replace(".", "").replace(",", "")
        try:
            data["mileage"] = int(mileage_str)
        except ValueError:
            pass

    return data


async def _handle_cookie_consent(page):
    """Try to handle common cookie consent banners."""
    consent_selectors = [
        'button[data-testid="uc-accept-all-button"]',
        'button[id*="accept"]',
        'button[class*="accept"]',
        'button:has-text("Accept all")',
        'button:has-text("Alle akzeptieren")',
        'button:has-text("Accept")',
        'button:has-text("OK")',
        '[class*="cookie"] button',
        '[id*="cookie"] button',
    ]

    for selector in consent_selectors:
        try:
            button = page.locator(selector).first
            if await button.is_visible(timeout=500):
                await button.click()
                await asyncio.sleep(0.5)
                break
        except Exception:
            continue


def _calculate_car_confidence(data: dict) -> float:
    """Calculate confidence score for car extraction."""
    score = 0.0
    weights = {
        "make": 0.2,
        "model": 0.2,
        "year": 0.15,
        "price": 0.15,
        "mileage": 0.1,
        "fuelType": 0.1,
        "transmission": 0.05,
        "power": 0.05,
    }

    for field, weight in weights.items():
        if data.get(field) is not None:
            score += weight

    return min(score, 1.0)


def _calculate_property_confidence(data: dict) -> float:
    """Calculate confidence score for property extraction."""
    score = 0.0
    weights = {
        "propertyType": 0.2,
        "size": 0.2,
        "price": 0.2,
        "rooms": 0.15,
        "location": 0.1,
        "postalCode": 0.1,
        "features": 0.05,
    }

    for field, weight in weights.items():
        value = data.get(field)
        if value is not None and value != [] and value != "":
            score += weight

    return min(score, 1.0)


def _calculate_travel_confidence(data: dict) -> float:
    """Calculate confidence score for travel extraction."""
    score = 0.0
    weights = {
        "travelType": 0.2,
        "hotelName": 0.2,
        "price": 0.2,
        "destination": 0.15,
        "duration": 0.1,
        "hotelStars": 0.1,
        "amenities": 0.05,
    }

    for field, weight in weights.items():
        value = data.get(field)
        if value is not None and value != [] and value != "":
            score += weight

    return min(score, 1.0)
