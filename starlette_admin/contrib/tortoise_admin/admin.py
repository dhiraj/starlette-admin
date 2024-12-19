from typing import Any, Dict, Optional, Sequence, Type

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import (
    FileResponse,
    JSONResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from starlette.routing import Mount, Route
from starlette_admin.auth import BaseAuthProvider
from starlette_admin.base import BaseAdmin
from starlette_admin.i18n import I18nConfig
from starlette_admin.i18n import lazy_gettext as _
from starlette_admin.views import CustomView

from .middleware import TortoiseMiddleware


class Admin(BaseAdmin):
    """Admin interface for TortoiseORM.
    
    This class extends the base admin interface to provide TortoiseORM-specific functionality.
    Database connection management is handled automatically through TortoiseMiddleware.

    Example:
        ```python
        from starlette.applications import Starlette
        from starlette_admin.contrib.tortoise_admin import Admin, ModelView

        app = Starlette()
        admin = Admin(
            db_url="sqlite://db.sqlite3",
            modules={"models": ["app.models"]},
            title="My Admin Site",
            generate_schemas=True  # Optional: create tables automatically
        )

        # Add views
        admin.add_view(ModelView(User))
        admin.add_view(ModelView(Post))

        # Mount admin
        admin.mount_to(app)
        ```
    """

    def __init__(
        self,
        db_url: str,
        modules: Dict[str, Sequence[str]],
        title: str = _("Admin"),
        base_url: str = "/admin",
        route_name: str = "admin",
        logo_url: Optional[str] = None,
        login_logo_url: Optional[str] = None,
        templates_dir: str = "templates",
        statics_dir: Optional[str] = None,
        index_view: Optional[CustomView] = None,
        auth_provider: Optional[BaseAuthProvider] = None,
        middlewares: Optional[Sequence[Middleware]] = None,
        debug: bool = False,
        i18n_config: Optional[I18nConfig] = None,
        favicon_url: Optional[str] = None,
        generate_schemas: bool = False,
        **db_init_kwargs: Any,
    ) -> None:
        """Initialize the admin interface.

        Args:
            db_url: Database URL (e.g., "sqlite://db.sqlite3")
            modules: Dictionary mapping module names to model paths
            title: Admin interface title
            base_url: Base URL for admin interface
            route_name: Name for the mounted admin app
            logo_url: URL for the admin logo
            login_logo_url: URL for the login page logo
            templates_dir: Directory for custom templates
            statics_dir: Directory for custom static files
            index_view: Custom view for the index page
            auth_provider: Authentication provider
            middlewares: Additional middleware to include
            debug: Enable debug mode
            i18n_config: Internationalization configuration
            favicon_url: URL for the favicon
            generate_schemas: Whether to generate database schemas
            **db_init_kwargs: Additional arguments passed to Tortoise.init
        """
        super().__init__(
            title=title,
            base_url=base_url,
            route_name=route_name,
            logo_url=logo_url,
            login_logo_url=login_logo_url,
            templates_dir=templates_dir,
            statics_dir=statics_dir,
            index_view=index_view,
            auth_provider=auth_provider,
            middlewares=middlewares,
            debug=debug,
            i18n_config=i18n_config,
            favicon_url=favicon_url,
        )
        self.middlewares = [] if self.middlewares is None else list(self.middlewares)
        self.middlewares.insert(
            0,
            Middleware(
                TortoiseMiddleware,
                db_url=db_url,
                modules=modules,
                generate_schemas=generate_schemas,
                **db_init_kwargs,
            ),
        )

    def mount_to(self, app: Starlette) -> None:
        """Mount the admin interface to a Starlette application."""
        try:
            # Add route to serve tortoise_file files if the package is installed
            __import__("tortoise_file")
            self.routes.append(
                Route(
                    "/api/file/{storage}/{file_id}",
                    self._serve_file,
                    methods=["GET"],
                    name="api:file",
                )
            )
        except ImportError:  # pragma: no cover
            pass
        super().mount_to(app)

    async def _serve_file(self, request: Request) -> Response:
        """Serve files stored with tortoise_file."""
        try:
            from tortoise_file.storage import StorageManager
            from tortoise_file.exceptions import FileNotFoundError

            try:
                storage = request.path_params.get("storage")
                file_id = request.path_params.get("file_id")
                file = await StorageManager.get_file(f"{storage}/{file_id}")

                if file.is_local:
                    # For local storage, return FileResponse
                    return FileResponse(
                        file.get_url(),
                        media_type=file.content_type,
                        filename=file.filename
                    )

                if file.has_public_url:
                    # For files with public URLs (e.g., S3), return the URL
                    return RedirectResponse(file.get_url())

                # For other storages, stream the file
                return StreamingResponse(
                    file.as_stream(),
                    media_type=file.content_type,
                    headers={"Content-Disposition": f"attachment;filename={file.filename}"},
                )
            except FileNotFoundError:
                return JSONResponse({"detail": "Not found"}, status_code=404)
        except ImportError:  # pragma: no cover
            return JSONResponse(
                {"detail": "tortoise_file package not installed"},
                status_code=500
            )
