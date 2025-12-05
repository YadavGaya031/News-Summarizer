from pydantic import BaseModel
from typing import Literal

class NewsRequest(BaseModel):
    topics: list[str]
    source_type: Literal["news","X","both"]
    
