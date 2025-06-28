import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import feedback, resource

app = FastAPI()


origins = [
    "http://localhost.tiangolo.com",
    "https://localhost.tiangolo.com",
    "http://localhost",
    "http://localhost:5173",
    "http://frontend",  # 使用服務名稱作為來源
    # "http://localhost:8080",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# app.include_router(api_router, prefix="/apis")
app.include_router(feedback.router, prefix="/api", tags=["feedback"])
app.include_router(resource.router, prefix="/api", tags=["resource"])



@app.get("/")
async def root():
    return {"message": "Welcome to my FastAPI project!"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
