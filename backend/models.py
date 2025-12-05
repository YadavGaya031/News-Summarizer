from pydantic import BaseModel
from typing import List, Literal

class NewsRequest(BaseModel):
    topics: List[str]
    source_type: Literal["news","X","both"]
    
