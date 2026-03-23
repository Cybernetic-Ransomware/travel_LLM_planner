from fastapi import HTTPException
from pydantic import BaseModel


class ErrorResponse(BaseModel):
    status_code: int
    error: str
    detail: str


class EndpointUnimplementedException(HTTPException):
    def __init__(self, message: str = ""):
        super().__init__(status_code=501, detail=f"Endpoint not implemented: {message}")


class EndpointUnexpectedException(HTTPException):
    def __init__(self, message: str = ""):
        super().__init__(status_code=500, detail=f"Unexpected Endpoint Error: {message}")
