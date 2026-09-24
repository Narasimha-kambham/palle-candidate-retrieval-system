from typing import Any, Dict, Optional
from pydantic import BaseModel
import logging

logger = logging.getLogger("pcrs")


class ErrorDetail(BaseModel):
    code: str
    stage: str
    message: str


class StructuredErrorResponse(BaseModel):
    error: ErrorDetail


class PipelineException(Exception):
    """Base exception for explicit stage failures in the recruitment pipeline."""
    def __init__(self, code: str, stage: str, message: str, status_code: int = 500, technical_details: Optional[str] = None):
        super().__init__(message)
        self.code = code
        self.stage = stage
        self.message = message
        self.status_code = status_code
        self.technical_details = technical_details

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "stage": self.stage,
                "message": self.message,
            }
        }


def classify_llm_exception(exc: Exception, stage: str = "jd_requirement_extraction") -> PipelineException:
    """
    Classifies LLM and provider exceptions into safe, structured PipelineException instances.
    Never exposes API keys, tokens, or raw credentials in the user-facing message.
    """
    exc_type = type(exc).__name__
    exc_str = str(exc).lower()

    # 1. Authentication / API Key errors
    if any(k in exc_type.lower() for k in ["auth", "unauthorized", "invalidapikey", "permissiondenied"]) or \
       any(k in exc_str for k in ["api key", "unauthorized", "401", "403", "permission denied", "authentication", "forbidden"]):
        return PipelineException(
            code="LLM_AUTHENTICATION_ERROR",
            stage=stage,
            message="AI service authentication failed. Please contact the administrator.",
            status_code=502,
            technical_details=f"{exc_type}: {exc}"
        )

    # 2. Rate limit / Quota exceeded errors
    if "ratelimit" in exc_type.lower() or "quota" in exc_str or "rate limit" in exc_str or "429" in exc_str or "resourceexhausted" in exc_str:
        return PipelineException(
            code="LLM_RATE_LIMIT_ERROR",
            stage=stage,
            message="AI service rate limit or quota has been exceeded. Please contact the administrator.",
            status_code=429,
            technical_details=f"{exc_type}: {exc}"
        )

    # 3. Provider unavailable / timeout / connection / exhausted errors
    if any(k in exc_type.lower() for k in ["providersexhausted", "connection", "timeout", "unavailable", "serviceunavailable"]) or \
       any(k in exc_str for k in ["503", "504", "unavailable", "timed out", "timeout", "connection refused", "exhausted"]):
        return PipelineException(
            code="LLM_PROVIDER_ERROR",
            stage=stage,
            message="AI service is currently unavailable. Please try again later.",
            status_code=503,
            technical_details=f"{exc_type}: {exc}"
        )

    # 4. Generic/Request LLM errors
    return PipelineException(
        code="LLM_REQUEST_ERROR",
        stage=stage,
        message="AI service request failed. Please contact the administrator if the problem continues.",
        status_code=502,
        technical_details=f"{exc_type}: {exc}"
    )

