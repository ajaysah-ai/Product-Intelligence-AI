from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import product, report, upload, validation

app = FastAPI(title="Product Intelligence AI", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten before real deployment
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload.router)
app.include_router(product.router)
app.include_router(validation.router)
app.include_router(report.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
