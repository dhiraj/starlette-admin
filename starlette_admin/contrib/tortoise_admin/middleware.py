from typing import Any, Dict, Optional, Sequence

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp
from tortoise import Tortoise, connections


class TortoiseMiddleware(BaseHTTPMiddleware):
    """Middleware for managing TortoiseORM database connections.
    
    This middleware ensures proper database connection management for each request.
    Unlike SQLAlchemy, TortoiseORM manages its own connection pool, so this middleware
    is mainly responsible for initializing the database if not already initialized.
    
    Example:
        ```python
        from starlette.applications import Starlette
        from starlette_admin.contrib.tortoise_admin import Admin, TortoiseMiddleware

        app = Starlette()
        admin = Admin()

        # Add middleware
        app.add_middleware(
            TortoiseMiddleware,
            db_url="sqlite://db.sqlite3",
            modules={"models": ["app.models"]}
        )

        # Mount admin
        admin.mount_to(app)
        ```
    """

    def __init__(
        self,
        app: ASGIApp,
        db_url: str,
        modules: Dict[str, Sequence[str]],
        generate_schemas: bool = False,
        **init_kwargs: Any
    ) -> None:
        """Initialize the middleware.
        
        Args:
            app: The ASGI application
            db_url: Database URL (e.g., "sqlite://db.sqlite3")
            modules: Dictionary mapping module names to model paths
            generate_schemas: Whether to generate database schemas
            **init_kwargs: Additional arguments passed to Tortoise.init
        """
        super().__init__(app)
        self.db_url = db_url
        self.modules = modules
        self.generate_schemas = generate_schemas
        self.init_kwargs = init_kwargs
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the database connection."""
        if not self._initialized:
            await Tortoise.init(
                db_url=self.db_url,
                modules=self.modules,
                **self.init_kwargs
            )
            if self.generate_schemas:
                await Tortoise.generate_schemas()
            self._initialized = True

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Handle the request and manage database connection."""
        await self.initialize()
        
        try:
            response = await call_next(request)
        except Exception:
            # Attempt to rollback any active transactions
            for conn_name in connections.db_config:
                try:
                    conn = connections.get(conn_name)
                    await conn.rollback()
                except Exception:
                    # Ignore any errors during rollback attempt
                    pass
            raise
            
        return response

    async def shutdown(self) -> None:
        """Close database connections."""
        if self._initialized:
            await Tortoise.close_connections()
            self._initialized = False
