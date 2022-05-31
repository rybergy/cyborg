import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel


class Config(BaseModel):
    cache_dir: Path = Path.cwd() / ".cache" / "cyborg"
    token: Optional[str] = os.getenv("CYBORG_TOKEN", None)

    def __init__(self, **data) -> None:
        super().__init__(**data)

        # Expanduser in case user passes in ~
        self.cache_dir = self.cache_dir.expanduser()
