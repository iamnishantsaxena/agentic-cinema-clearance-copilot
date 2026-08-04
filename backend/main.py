from fastapi import FastAPI

app = FastAPI(title="Clearance Copilot")


@app.get("/health")
async def health():
    return {"status": "ok"}
