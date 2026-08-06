from fastapi import FastAPI

app = FastAPI(title="cicd-pipeline-demo")


@app.get("/")
def read_root():
    return {"message": "Hello from cicd-pipeline-demo"}


@app.get("/health")
def health():
    return {"status": "ok"}