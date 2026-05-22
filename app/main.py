from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.database import create_tables
from app.routers import auth, documents, ideas, diff, merge_queue, master_doc, notifications, settings, admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    yield


app = FastAPI(
    title="SmartDocMerger API",
    version="1.0.0",
    description="Document deduplication and synthesis backend",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production: ["https://smartdocmerger.vercel.app"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(ideas.router)
app.include_router(diff.router)
app.include_router(merge_queue.router)
app.include_router(master_doc.router)
app.include_router(notifications.router)
app.include_router(settings.router)
app.include_router(admin.router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "SmartDocMerger"}


@app.get("/")
async def root():
    return {"message": "SmartDocMerger API", "docs": "/docs"}
