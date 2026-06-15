from pydantic import BaseModel


class BuildResult(BaseModel):
    app_path: str
    files_created: list[str]
    warnings: list[str]
    build_id: str
