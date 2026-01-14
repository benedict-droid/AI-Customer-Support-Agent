from fastapi import APIRouter

import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/health", tags=["Health"])
async def health_check():
    logger.info("Health check endpoint called")
    return {"status": "ok"}
