from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.orm import Session
from app.api.admin_routes import create_admin_log
from app.database.postgresql import get_db
import json
import re

class AdminLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Only log admin routes
        if not request.url.path.startswith("/postgres/") and not request.url.path.startswith("/admin/"):
            return await call_next(request)

        # Skip logging for the logs endpoint itself to avoid recursion
        if request.url.path == "/admin/logs":
            return await call_next(request)

        # Get database session
        db = next(get_db())

        try:
            # Store request body for logging if needed
            body = None
            if request.method in ["POST", "PUT", "PATCH"]:
                try:
                    body = await request.json()
                except:
                    pass

            # Process the request
            response = await call_next(request)

            # Determine action type from HTTP method
            action_map = {
                "GET": "read",
                "POST": "create",
                "PUT": "update",
                "PATCH": "update",
                "DELETE": "delete"
            }
            action = action_map.get(request.method, "other")

            # Extract resource type from URL
            resource_type = self._extract_resource_type(request.url.path)

            # Extract resource ID from URL if present
            resource_id = self._extract_resource_id(request.url.path)

            # Create details message
            details = self._create_details_message(
                request.method,
                request.url.path,
                json.dumps(body) if body else None,
                resource_type,
                resource_id
            )

            # Determine status based on response status code
            status = "success" if response.status_code < 400 else "failure"

            # Get previous and new state for update operations
            previous_state = None
            new_state = None
            if action == "update" and body:
                new_state = body
                # Note: Previous state would need to be fetched from the database
                # This is just a placeholder - implement based on your needs
                previous_state = {}

            # Create log entry
            await create_admin_log(
                db=db,
                user_id=request.state.user_id if hasattr(request.state, "user_id") else "system",
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                details=details,
                request=request,
                status=status,
                previous_state=previous_state,
                new_state=new_state
            )

            return response

        except Exception as e:
            # Log the error but don't block the request
            try:
                await create_admin_log(
                    db=db,
                    user_id=request.state.user_id if hasattr(request.state, "user_id") else "system",
                    action=action_map.get(request.method, "other"),
                    resource_type=self._extract_resource_type(request.url.path),
                    resource_id=self._extract_resource_id(request.url.path),
                    details=f"Error processing request: {str(e)}",
                    request=request,
                    status="failure"
                )
            except:
                pass  # Suppress any errors in error logging
            raise

    def _extract_resource_type(self, path: str) -> str:
        """Extract resource type from URL path."""
        # Remove prefix and trailing slashes
        path = path.strip("/")
        parts = path.split("/")

        # Map URL parts to resource types
        resource_map = {
            "faq": "FAQ",
            "emergency": "EmergencyContact",
            "events": "Event",
            "about": "AboutPixity",
            "solana-summit": "SolanaSummit",
            "danang-bucket-list": "DanangBucketList",
            "api-keys": "ApiKey",
            "vector-databases": "VectorDatabase",
            "documents": "Document",
            "telegram-bots": "TelegramBot",
            "chat-engines": "ChatEngine",
            "bot-engines": "BotEngine",
            "users": "User",
            "config": "Config"
        }

        # Try to find a matching resource type
        for part in parts:
            if part in resource_map:
                return resource_map[part]

        return "Unknown"

    def _extract_resource_id(self, path: str) -> str:
        """Extract resource ID from URL path."""
        # Look for ID patterns in the URL
        id_pattern = r"/(\d+)(?:/|$)"
        match = re.search(id_pattern, path)
        return match.group(1) if match else None

    def _create_details_message(
        self,
        method: str,
        path: str,
        body: str,
        resource_type: str,
        resource_id: str
    ) -> str:
        """Create a human-readable details message."""
        action_words = {
            "GET": "Retrieved",
            "POST": "Created",
            "PUT": "Updated",
            "PATCH": "Modified",
            "DELETE": "Deleted"
        }

        action_word = action_words.get(method, "Accessed")
        resource_desc = f"{resource_type}"
        if resource_id:
            resource_desc += f" #{resource_id}"

        details = f"{action_word} {resource_desc}"

        # Add relevant request body information for create/update operations
        if body and method in ["POST", "PUT", "PATCH"]:
            try:
                data = json.loads(body)
                if isinstance(data, dict):
                    # Add name or title if available
                    if "name" in data:
                        details += f": {data['name']}"
                    elif "title" in data:
                        details += f": {data['title']}"
            except:
                pass

        return details 