from pydantic import BaseModel
from typing import List, Optional


class ApproveExpenseRequest(BaseModel):
    role: str
