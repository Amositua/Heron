from pydantic import BaseModel


class ValidationCheck(BaseModel):
    name: str
    passed: bool
    detail: str


class ValidationReport(BaseModel):
    passed: bool
    checks: list[ValidationCheck]


class DeployResult(BaseModel):
    success: bool
    app_name: str
    app_path: str
    actions: list[str] = []
    validation: ValidationReport | None = None
    rolled_back: bool = False
    error: str | None = None
