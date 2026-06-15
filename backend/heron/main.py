from fastapi import FastAPI

app = FastAPI(title="Heron")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "heron"}
