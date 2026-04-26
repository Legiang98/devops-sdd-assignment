from pydantic import BaseModel
from typing import List, Optional


class SubmitExpenseRequest(BaseModel):
    amount: float = Field(gt=0)
    description: str


def required_stages_for_amount(amount: float, rules: dict) -> List[str]:
    stages = []
    for stage in rules["workflow"]["stages"]:
        threshold = float(stage["required_when"]["amount_gte"])
        if amount >= threshold:
            stages.append(stage["name"])
    return stages
