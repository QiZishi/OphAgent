# app/agents/schemas.py
"""智能体响应模型定义"""

from pydantic import BaseModel, Field
from typing import List, Tuple

class Box(BaseModel):
    label: str
    coords: Tuple[int, int, int, int]  # (x_min, y_min, x_max, y_max)
    confidence: float = Field(..., ge=0.0, le=1.0)

class LesionLocalizationResponse(BaseModel):
    image_url: str
    boxes: List[Box]

class Diagnosis(BaseModel):
    condition: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str

class DiagnosticAssistantResponse(BaseModel):
    diagnoses: List[Diagnosis]
