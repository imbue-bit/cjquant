from dataclasses import dataclass
from typing import Dict

@dataclass
class ExposureResult:
    fund_code: str
    analysis_date: str
    method: str  # 'HBA' or 'RBSA'
    exposures: Dict[str, float]
    r_squared: float = 1.0       # 解释度 (仅RBSA有效)