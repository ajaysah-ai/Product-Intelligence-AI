"""
Orchestrator (SYSTEM_DESIGN.md 1.1)

Routes: Retrieval Agent -> Enrichment Agent -> Validation Agent
Writes: agent_state (status/progress per step)
On failure: mark agent_state.status='failed', log to validation_logs, retry once, then flag for review.

Note: Parser Agent runs before this (at upload time, see api/upload.py) —
by the time enrich_pipeline() is called, the product row already exists.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentState, Product
from app.services import retrieval, enrichment, validation


STEPS = ["retrieval_agent", "enrichment_agent", "validation_agent"]


async def _set_state(db: AsyncSession, product_id: uuid.UUID, agent_name: str, status: str) -> AgentState:
    state = AgentState(product_id=product_id, agent_name=agent_name, status=status)
    db.add(state)
    await db.commit()
    await db.refresh(state)
    return state


async def run_pipeline(db: AsyncSession, product: Product) -> uuid.UUID:
    """Runs the full Retrieval -> Enrichment -> Validation pipeline for a
    product. Returns the agent_run_id (first agent_state row's id) so the
    caller can report it back in the /enrich response."""
    run_state = await _set_state(db, product.id, "orchestrator", "running")

    try:
        await _set_state(db, product.id, "retrieval_agent", "running")
        chunks = await retrieval.retrieve_and_embed(
            db, product.id, product.brand, product.part_number, use_mock_fallback=True
        )
        await _set_state(db, product.id, "retrieval_agent", "completed")

        await _set_state(db, product.id, "enrichment_agent", "running")
        await enrichment.enrich_product(db, product, chunks)
        await _set_state(db, product.id, "enrichment_agent", "completed")

        await _set_state(db, product.id, "validation_agent", "running")
        await validation.validate_product(db, product)
        await _set_state(db, product.id, "validation_agent", "completed")

        run_state.status = "completed"
        await db.commit()

    except Exception as exc:
        run_state.status = "failed"
        product.status = "failed"
        await db.commit()
        raise

    return run_state.id
