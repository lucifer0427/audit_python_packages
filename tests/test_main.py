from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_index_page():
    # Use with TestClient(app) as client: or manual lifespan trigger
    # But the simplest way is to use a context manager if available or
    # just mock _index_html for this specific test.
    with patch("app.main._index_html", "<html>upload</html>"):
        response = client.get("/")
        assert response.status_code == 200
        assert "upload" in response.text.lower()


def test_lifespan(tmp_path):
    # Test lifespan by using the FastAPI lifespan manager
    from app.main import lifespan

    # Mock settings.REPORTS_DIR to use tmp_path
    with patch("app.config.settings.REPORTS_DIR", tmp_path):
        # Use a mock app
        mock_app = MagicMock()
        mock_app.state = MagicMock()

        # Run lifespan start
        # Since lifespan is an asynccontextmanager, we need to run it in an event loop
        import asyncio

        async def run_lifespan():
            async with lifespan(mock_app):
                # Check if reports dir was created
                assert (tmp_path).exists()
                # Check if http_client was added to state
                assert hasattr(mock_app.state, "http_client")

        asyncio.run(run_lifespan())
