"""
Signature Utils Module
"""

import hmac
import hashlib
import logging
import time
import secrets
import json
from typing import Dict, Any

from .exceptions import SignatureError

logger = logging.getLogger(__name__)


class SignatureUtils:
    """Signature utility class"""

    @staticmethod
    def generate_nonce() -> str:
        """Generate 32-bit random number"""
        return secrets.token_hex(16)

    @staticmethod
    def generate_timestamp() -> str:
        """Generate 13-bit millisecond timestamp"""
        return str(int(time.time() * 1000))

    @staticmethod
    def generate_conn_id() -> str:
        """Generate connection ID in UUID format"""
        import uuid

        return str(uuid.uuid4())

    @staticmethod
    def calculate_signature(
        access_secret: str,
        access_id: str,
        nonce: str,
        timestamp: str,
        path: str = "/ws/mcp",
        body: str = "",
        signature_headers: str = "",
        headers: Dict[str, str] | None = None,
        query_params: Dict[str, str] | None = None,
    ) -> str:
        """
        Calculate WebSocket signature for MCP Gateway

        Args:
            access_secret: Access Secret
            access_id: Access ID
            nonce: Random number (32-bit)
            timestamp: Timestamp (13-bit millisecond)
            path: WebSocket path
            body: Request body (empty for WebSocket)
            signature_headers: Headers to include in signature (colon-separated)
            headers: Additional request headers
            query_params: Query parameters (contains cid for WebSocket)

        Returns:
            Signature string (uppercase)
        """
        # Step 1: Build Headers part
        headers_str = ""
        if signature_headers and headers:
            header_keys = signature_headers.split(":")
            header_parts = []
            for key in header_keys:
                if key in headers:
                    header_parts.append(f"{key}:{headers[key]}")
            if header_parts:
                headers_str = "\n".join(header_parts)

        # Step 2: Build Querys part
        querys_str = ""
        if query_params:
            query_parts = []
            for key, value in sorted(query_params.items()):
                query_parts.append(f"{key}={value}")
            if query_parts:
                querys_str = "&".join(query_parts)

        # Step 3: Build headerPathStr = Headers + "\n" + Querys + "\n"
        header_path_str = headers_str + "\n" + querys_str + "\n"

        # Step 4: Build bodyByteStr = string([]byte(OriginalBody)) + "\n" + URL
        body_byte_str = body + "\n" + path

        # Step 5: Build stringToSign = access_id + "\n" + t + "\n" + sign_method + "\n" + nonce + "\n" + headerPathStr + "\n" + bodyByteStr
        string_to_sign = f"{access_id}\n{timestamp}\nHMAC-SHA256\n{nonce}\n{header_path_str}{body_byte_str}"

        # Debug: Log signature components (only in DEBUG level to protect sensitive data)
        logger.debug("WebSocket Signature Components:")
        logger.debug("  access_id: %s", access_id)
        logger.debug("  timestamp: %s", timestamp)
        logger.debug("  nonce: %s", nonce)
        logger.debug("  headers_str: '%s'", headers_str)
        logger.debug("  querys_str: '%s'", querys_str)
        logger.debug("  header_path_str: '%s'", header_path_str)
        logger.debug("  body_byte_str: '%s'", body_byte_str)
        logger.debug("  string_to_sign: '%s'", string_to_sign)
        logger.debug("  string_to_sign (repr): %r", string_to_sign)

        # Step 6: Calculate HMAC-SHA256 signature and convert to uppercase
        signature = (
            hmac.new(
                access_secret.encode("utf-8"),
                string_to_sign.encode("utf-8"),
                hashlib.sha256,
            )
            .hexdigest()
            .upper()
        )

        logger.debug("  calculated_signature: %s", signature)

        return signature

    @staticmethod
    def verify_signature(
        access_secret: str,
        received_signature: str,
        access_id: str,
        nonce: str,
        timestamp: str,
        path: str = "/ws/mcp",
        body: str = "",
        signature_headers: str = "",
        headers: Dict[str, str] | None = None,
        query_params: Dict[str, str] | None = None,
    ) -> bool:
        """
        Verify WebSocket signature for MCP Gateway

        Args:
            access_secret: Access Secret
            received_signature: Received signature
            access_id: Access ID
            nonce: Random number (32-bit)
            timestamp: Timestamp (13-bit millisecond)
            path: WebSocket path
            body: Request body (empty for WebSocket)
            signature_headers: Headers to include in signature (colon-separated)
            headers: Additional request headers
            query_params: Query parameters (contains cid for WebSocket)

        Returns:
            Verification result
        """
        try:
            calculated_signature = SignatureUtils.calculate_signature(
                access_secret=access_secret,
                access_id=access_id,
                nonce=nonce,
                timestamp=timestamp,
                path=path,
                body=body,
                signature_headers=signature_headers,
                headers=headers,
                query_params=query_params,
            )
            return hmac.compare_digest(received_signature.upper(), calculated_signature)
        except Exception as e:
            raise SignatureError(f"signature verification failed: {e}") from e

    @staticmethod
    def create_websocket_headers(
        access_id: str,
        access_secret: str,
        client_id: str,
        path: str = "/ws/mcp",
        signature_headers: str = "",
        extra_headers: Dict[str, str] | None = None,
    ) -> Dict[str, str]:
        """
        Create WebSocket connection headers for MCP Gateway

        Args:
            access_id: Access ID
            access_secret: Access Secret
            cid: Client ID (will be added as query parameter)
            path: WebSocket path
            signature_headers: Headers to include in signature (colon-separated)
            extra_headers: Additional request headers

        Returns:
            Dictionary of headers with signature
        """
        nonce = SignatureUtils.generate_nonce()
        timestamp = SignatureUtils.generate_timestamp()

        # Prepare headers for signature calculation
        headers_for_signature = {}
        if extra_headers:
            headers_for_signature.update(extra_headers)

        # Prepare query parameters
        query_params = {"client_id": client_id}

        signature = SignatureUtils.calculate_signature(
            access_secret=access_secret,
            access_id=access_id,
            nonce=nonce,
            timestamp=timestamp,
            path=path,
            body="",  # Empty body for WebSocket
            signature_headers=signature_headers,
            headers=headers_for_signature,
            query_params=query_params,
        )

        headers = {
            "access_id": access_id,
            "sign_method": "HMAC-SHA256",
            "nonce": nonce,
            "t": timestamp,
            "sign": signature,
        }

        # Add Signature-Headers if specified
        if signature_headers:
            headers["Signature-Headers"] = signature_headers

        if extra_headers:
            headers.update(extra_headers)

        return headers

    @staticmethod
    def create_auth_headers(
        access_id: str,
        access_secret: str,
        uri: str = "/v1/client/registration",
        body: str = "",
        extra_headers: Dict[str, str] | None = None,
    ) -> Dict[str, str]:
        """
        Create authentication request headers (for HTTP API calls)

        Args:
            access_id: Access ID
            access_secret: Access Secret
            uri: Request URI
            body: Request body
            extra_headers: Additional request headers

        Returns:
            Dictionary of headers with signature
        """
        nonce = SignatureUtils.generate_nonce()
        timestamp = SignatureUtils.generate_timestamp()

        # Step 1: Build Headers part (no signature headers for HTTP requests currently)
        headers_str = ""

        # Step 2: Build Querys part (empty for HTTP requests)
        querys_str = ""

        # Step 3: Build headerPathStr = Headers + "\n" + Querys + "\n"
        header_path_str = headers_str + "\n" + querys_str + "\n"

        # Step 4: Build bodyByteStr = string([]byte(OriginalBody)) + "\n" + URL
        body_byte_str = body + "\n" + uri

        # Step 5: Build stringToSign = access_id + "\n" + t + "\n" + sign_method + "\n" + nonce + "\n" + headerPathStr + "\n" + bodyByteStr
        string_to_sign = f"{access_id}\n{timestamp}\nHMAC-SHA256\n{nonce}\n{header_path_str}{body_byte_str}"

        # Debug: Log signature components for HTTP auth (only in DEBUG level to protect sensitive data)
        logger.debug("HTTP Auth Signature Components:")
        logger.debug("  access_id: %s", access_id)
        logger.debug("  timestamp: %s", timestamp)
        logger.debug("  nonce: %s", nonce)
        logger.debug("  uri: %s", uri)
        logger.debug("  body: '%s'", body)
        logger.debug("  headers_str: '%s'", headers_str)
        logger.debug("  querys_str: '%s'", querys_str)
        logger.debug("  header_path_str: '%s'", header_path_str)
        logger.debug("  body_byte_str: '%s'", body_byte_str)
        logger.debug("  string_to_sign: '%s'", string_to_sign)
        logger.debug("  string_to_sign (repr): %r", string_to_sign)

        # Step 6: Calculate HMAC-SHA256 signature and convert to uppercase
        signature = (
            hmac.new(
                access_secret.encode("utf-8"),
                string_to_sign.encode("utf-8"),
                hashlib.sha256,
            )
            .hexdigest()
            .upper()
        )

        logger.debug("  calculated_signature: %s", signature)

        headers = {
            "access_id": access_id,
            "sign_method": "HMAC-SHA256",
            "nonce": nonce,
            "t": timestamp,
            "sign": signature,
        }

        if extra_headers:
            headers.update(extra_headers)

        return headers

    @staticmethod
    def create_message_signature(
        access_secret: str, message_data: Dict[str, Any]
    ) -> str:
        """
        Create signature for WebSocket message sending

        Args:
            access_secret: Access Secret
            message_data: Message data dictionary (excluding 'sign' field)

        Returns:
            Signature string (uppercase)
        """
        # Remove 'sign' field if present
        filtered_data = {k: v for k, v in message_data.items() if k != "sign"}

        # Sort keys by ASCII order
        sorted_keys = sorted(filtered_data.keys())

        # Build string format: key1=value1\nkey2=value2
        params = []
        for key in sorted_keys:
            value = filtered_data[key]
            # Convert value to string
            if isinstance(value, (dict, list)):
                value_str = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
            else:
                value_str = str(value)

            # URL encode the value
            params.append(f"{key}:{value_str}")

        # Join with \n
        query_string = "\n".join(params)

        # Debug: Log message signature components (only in DEBUG level to protect sensitive data)
        logger.debug("Message Signature Components:")
        logger.debug("  sorted_keys: %s", sorted_keys)
        logger.debug("  params: %s", params)
        logger.debug("  query_string: '%s'", query_string)
        logger.debug("  query_string (repr): %r", query_string)

        # Calculate HMAC-SHA256 signature and convert to uppercase
        signature = (
            hmac.new(
                access_secret.encode("utf-8"),
                query_string.encode("utf-8"),
                hashlib.sha256,
            )
            .hexdigest()
            .upper()
        )

        logger.debug("  calculated_signature: %s", signature)

        return signature

    @staticmethod
    def sign_message(
        access_secret: str, message_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Sign WebSocket message data

        Args:
            access_secret: Access Secret
            message_data: Message data dictionary

        Returns:
            Message data with signature added
        """
        # Create a copy to avoid modifying original data
        signed_message = message_data.copy()

        # Generate signature
        signature = SignatureUtils.create_message_signature(access_secret, message_data)

        # Add signature to message
        signed_message["sign"] = signature

        return signed_message

    @staticmethod
    def verify_message_signature(
        access_secret: str, message_data: Dict[str, Any]
    ) -> bool:
        """
        Verify WebSocket message signature

        Args:
            access_secret: Access Secret
            message_data: message data dictionary (including 'sign' field)

        Returns:
            Verification result
        """
        try:
            # Extract received signature
            received_signature = message_data.get("sign", "")
            if not received_signature:
                return False

            # Calculate expected signature
            expected_signature = SignatureUtils.create_message_signature(
                access_secret, message_data
            )

            # Compare signatures
            return hmac.compare_digest(received_signature.upper(), expected_signature)
        except Exception as e:
            raise SignatureError(f"Message signature verification failed: {e}") from e
