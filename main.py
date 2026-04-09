import os
from pydantic import BaseModel, HttpUrl
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Import services
from services.quote_calculation import (
    calculate_quote,
    get_extras,
    get_tier_definitions,
    QuoteParams
)
from services.link_preview import fetch_link_preview

# Load environment variables from .env.local for local development
if os.path.exists(".env.local"):
    load_dotenv(".env.local")
else:
    load_dotenv()

app = FastAPI(
    title="anpost-insurance API",
    description="Backend API for anpost-insurance",
    version="1.0.0"
)


class ExtractDataRequest(BaseModel):
    url: HttpUrl

# Get CORS origins from environment variable
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {
        "message": "Welcome to anpost-insurance API",
        "version": "1.0.0",
        "environment": os.getenv("ENVIRONMENT", "development")
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "environment": os.getenv("ENVIRONMENT", "development")
    }

@app.get("/api/example")
async def example_endpoint():
    return {
        "message": "This is an example endpoint",
        "data": ["item1", "item2", "item3"]
    }


# BRAND: An Post Insurance Quote Endpoints
@app.post("/api/quote/calculate")
async def calculate_quote_endpoint(params: QuoteParams):
    """
    Calculate car insurance quote with Irish pricing rules
    Returns tier options and insurer panel
    """
    try:
        result = calculate_quote(params)
        return {
            "success": True,
            "data": result.model_dump()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Quote calculation failed: {str(e)}")


@app.get("/api/products/extras")
async def get_extras_endpoint():
    """
    Get available optional extras (Motor Legal, Keycare, etc.)
    """
    return {
        "success": True,
        "data": get_extras()
    }


@app.get("/api/products/tiers")
async def get_tiers_endpoint(product_type: str = Query(default="car")):
    """
    Get tier definitions for a product type
    """
    tiers = get_tier_definitions(product_type)
    if not tiers:
        raise HTTPException(status_code=404, detail=f"Product type '{product_type}' not found")

    return {
        "success": True,
        "data": tiers
    }


@app.get("/api/link-preview")
async def link_preview_endpoint(url: str = Query(..., description="URL to preview")):
    """
    Fetch link preview (title, description, image) for a given URL.
    Returns a safe fallback object when upstream sites are unreachable.
    """
    try:
        preview = await fetch_link_preview(url)
        return {
            "success": True,
            "data": preview.model_dump()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Link preview failed: {str(e)}")


@app.post("/api/extract-data")
async def extract_data_endpoint(request: ExtractDataRequest):
    """
    Extract structured data from a URL (vehicle details, property info, travel info).
    """
    try:
        preview = await fetch_link_preview(str(request.url))
        result = {
            "url": str(request.url),
            "contentType": preview.contentType,
            "structured": {},
            "rawText": f"{preview.title or ''} {preview.description or ''}".strip(),
            "confidence": 0.2 if (preview.title or preview.description) else 0.0,
            "error": "Deep extraction unavailable in this deployment; returning preview-derived fallback.",
        }
        return {
            "success": True,
            "data": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Data extraction failed: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 5010))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
