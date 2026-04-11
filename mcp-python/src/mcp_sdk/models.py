"""
Data Model Definitions
"""

from typing import Optional
from pydantic import BaseModel, Field


class AuthConfig(BaseModel):
    """Authentication Configuration"""
    endpoint: str = Field(..., description="MCPSdk domain")
    access_id: str = Field(..., description="Developer access ID")
    access_secret: str = Field(..., description="Developer access secret")


class TokenResponse(BaseModel):
    """Token Response"""
    success: bool = Field(..., description="Whether request succeeded")
    msg: Optional[str] = Field(None, description="Request response message")
    data: Optional["TokenData"] = Field(None, description="Response data body")
    error_code: Optional[str] = Field(
        None, description="Error code when success is false")
    error_msg: Optional[str] = Field(
        None, description="Error message when success is false")


class TokenData(BaseModel):
    """Token Data"""
    token: str = Field(..., description="Token value")
    client_id: str = Field(..., description="Client UUID")


class MCPSdkRequest(BaseModel):
    """MCPSdk Request Format"""
    request_id: str = Field(..., description="Request ID")
    endpoint: str = Field(
        "", description="Endpoint, empty string or streamable")
    version: str = Field("v1", description="Version number")
    method: str = Field(..., description="Method name, e.g., tools/call")
    ts: str = Field(..., description="Timestamp")
    request: str = Field(..., description="Request data as JSON string")
    sign: Optional[str] = Field(
        None, description="Message signature, not included in signing")
    meta: Optional[dict] = Field(
        None, description="Meta information from WebSocket message")


class MCPSdkResponse(BaseModel):
    """MCPSdk Response Format"""
    request_id: str = Field(..., description="Request ID")
    endpoint: str = Field("", description="Endpoint, empty string or URL")
    version: str = Field("v1", description="Version number")
    method: Optional[str] = Field(
        None, description="Method name, e.g., tools/call")
    ts: Optional[str] = Field(None, description="Timestamp")
    response: str = Field(..., description="Response data as JSON string")
    sign: Optional[str] = Field(
        None, description="Message signature, not included in signing")


class SignatureHeaders(BaseModel):
    """Signature Request Headers"""
    access_id: str = Field(..., description="Developer access ID")
    sign_method: str = Field("HMAC-SHA256", description="Signature algorithm")
    nonce: str = Field(..., description="32-bit random number")
    t: str = Field(..., description="13-bit millisecond timestamp")
    sign: str = Field(..., description="Signature result")


# Update TokenResponse forward reference
TokenResponse.model_rebuild()
