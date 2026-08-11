from fastapi import FastAPI

from .routes import router

app = FastAPI(
    title="Quant Primitives Service",
    description=(
        "Deterministic financial computations (alpha, beta, VaR, correlation, "
        "drift, concentration) for the Retail Research Platform's Intelligence "
        "Layer. Currently reads fixture data -- see ../fixtures_store.py and "
        "the repo README for what that means and where the real vendor "
        "integration will land."
    ),
    version="0.1.0",
)
app.include_router(router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
