import os
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
# TODO: Enable when playwright/greenlet compatibility resolved
# from services.link_preview import fetch_link_preview
# from services.data_extraction import extract_data

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


# TEMPLATE: Link Preview and Data Extraction Endpoints
# TODO: Enable when playwright/greenlet compatibility resolved
# @app.get("/api/link-preview")
# async def link_preview_endpoint(url: str = Query(..., description="URL to preview")):
#     """
#     Fetch link preview (title, description, image) for a given URL
#     """
#     try:
#         preview = await fetch_link_preview(url)
#         return {
#             "success": True,
#             "data": preview
#         }
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Link preview failed: {str(e)}")


# @app.post("/api/extract-data")
# async def extract_data_endpoint(request: dict):
#     """
#     Extract structured data from a URL (vehicle details, driver info, etc.)
#     """
#     try:
#         url = request.get("url")
#         if not url:
#             raise HTTPException(status_code=400, detail="URL is required")

#         result = await extract_data(url)
#         return {
#             "success": True,
#             "data": result
#         }
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Data extraction failed: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 5010))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
