from fastapi import APIRouter

from app.engine import generate_plan
from app.models import Plan, PlanRequest

router = APIRouter(tags=["planner"])


@router.post("/plan", response_model=Plan)
async def create_plan(req: PlanRequest):
    plan = await generate_plan(
        prompt=req.prompt,
        input_format=req.input_format,
        output_format=req.output_format,
    )
    return plan
