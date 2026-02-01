from fastapi import FastAPI

app = FastAPI(title="Anonymous Signal API")

@app.get("/")
def root():
    return {"status": "Anonymous Signal API running"}

@app.get("/health")
def health():
    return {"health": "ok"}
