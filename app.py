import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from main import app
import uvicorn

# Load environment variables
load_dotenv()

# Import routers
try:
    from app.api.mongodb_routes import router as mongodb_router
    from app.api.postgresql_routes import router as postgresql_router
    from app.api.rag_routes import router as rag_router
    from app.api.websocket_routes import router as websocket_router
except ImportError as e:
    print(f"Error importing routes: {e}")
    raise

# Create FastAPI app
app = FastAPI(
    title="PIX Project Backend API",
    description="Backend API for PIX Project with MongoDB, PostgreSQL and RAG integration",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(mongodb_router)
app.include_router(postgresql_router)
app.include_router(rag_router)
app.include_router(websocket_router)

# Root endpoint
@app.get("/")
def read_root():
    return {
        "message": "Welcome to PIX Project Backend API",
        "documentation": "/docs",
    }

# Health check endpoint
@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "version": "1.0.0",
        "environment": os.environ.get("ENVIRONMENT", "production")
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860) 