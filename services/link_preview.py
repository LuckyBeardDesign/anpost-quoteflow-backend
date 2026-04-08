"""
Link Preview Service - Fast OG metadata extraction for URL cards
Uses httpx + BeautifulSoup for ~300ms response times
"""

import re
from urllib.parse import urlparse, urljoin
from typing import Optional
import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel


class LinkPreviewData(BaseModel):
    url: str
    title: Optional[str] = None
    description: Optional[str] = None
    image: Optional[str] = None
    favicon: Optional[str] = None
    siteName: Optional[str] = None
    contentType: str = "unknown"


# URL patterns for content type detection
CONTENT_TYPE_PATTERNS = {
    "car_listing": [
        r"autoscout24\.",
        r"mobile\.de",
        r"mercedes-benz\.",
        r"bmw\.",
        r"audi\.",
        r"volkswagen\.",
        r"porsche\.",
        r"tesla\.",
        r"carwow\.",
        r"auto\.",
        r"/car/",
        r"/fahrzeug/",
        r"/vehicle/",
    ],
    "property_listing": [
        r"immoscout24\.",
        r"immowelt\.",
        r"immonet\.",
        r"immobilien\.",
        r"/property/",
        r"/haus/",
        r"/wohnung/",
        r"/apartment/",
        r"zillow\.",
        r"rightmove\.",
    ],
    "travel_listing": [
        r"booking\.com",
        r"expedia\.",
        r"tui\.",
        r"hotels\.com",
        r"airbnb\.",
        r"/hotel/",
        r"/holiday/",
        r"/urlaub/",
        r"/travel/",
        r"/flight/",
    ],
}


def detect_content_type(url: str) -> str:
    """Detect the content type based on URL patterns."""
    url_lower = url.lower()
    for content_type, patterns in CONTENT_TYPE_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, url_lower):
                return content_type
    return "unknown"


def resolve_url(base_url: str, relative_url: Optional[str]) -> Optional[str]:
    """Resolve a potentially relative URL to an absolute URL."""
    if not relative_url:
        return None
    if relative_url.startswith(("http://", "https://", "//")):
        if relative_url.startswith("//"):
            return f"https:{relative_url}"
        return relative_url
    return urljoin(base_url, relative_url)


def extract_favicon(soup: BeautifulSoup, base_url: str) -> Optional[str]:
    """Extract favicon URL from HTML."""
    # Try various favicon link types
    for rel in ["icon", "shortcut icon", "apple-touch-icon"]:
        link = soup.find("link", rel=lambda x: x and rel in x.lower() if isinstance(x, str) else rel in " ".join(x).lower() if x else False)
        if link and link.get("href"):
            return resolve_url(base_url, link["href"])

    # Default to /favicon.ico
    parsed = urlparse(base_url)
    return f"{parsed.scheme}://{parsed.netloc}/favicon.ico"


async def fetch_link_preview(url: str) -> LinkPreviewData:
    """
    Fetch Open Graph metadata from a URL.
    Returns preview data including title, description, image, and favicon.
    """
    content_type = detect_content_type(url)

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5,de;q=0.3",
    }

    async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
        except httpx.HTTPError as e:
            return LinkPreviewData(
                url=url,
                contentType=content_type,
                title="Unable to load preview",
            )

        soup = BeautifulSoup(response.text, "lxml")

        # Extract Open Graph metadata
        og_title = soup.find("meta", property="og:title")
        og_description = soup.find("meta", property="og:description")
        og_image = soup.find("meta", property="og:image")
        og_site_name = soup.find("meta", property="og:site_name")

        # Fallback to standard meta tags
        title = (
            og_title["content"] if og_title and og_title.get("content")
            else soup.title.string if soup.title else None
        )

        description = (
            og_description["content"] if og_description and og_description.get("content")
            else None
        )
        if not description:
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc and meta_desc.get("content"):
                description = meta_desc["content"]

        image = (
            og_image["content"] if og_image and og_image.get("content")
            else None
        )
        image = resolve_url(url, image)

        site_name = (
            og_site_name["content"] if og_site_name and og_site_name.get("content")
            else urlparse(url).netloc
        )

        favicon = extract_favicon(soup, url)

        return LinkPreviewData(
            url=url,
            title=title,
            description=description,
            image=image,
            favicon=favicon,
            siteName=site_name,
            contentType=content_type,
        )
