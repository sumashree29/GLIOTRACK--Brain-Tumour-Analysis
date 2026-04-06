from pydantic import BaseModel
from typing import Optional

class ReportRecord(BaseModel):
    scan_id: str
    r2_key: str
    generation_ts: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    download_url: Optional[str] = None
