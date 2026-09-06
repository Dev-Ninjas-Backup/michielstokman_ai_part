from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.rate_limit import enforce_rate_limit
from app.core.security import create_access_token
from app.model.story import AssetReviewStatus, Story
from app.services.service_member_story import public_story_share_url


def test_production_requires_secret_key(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://transformtoliberation.com")
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        Settings()


def test_production_rejects_wildcard_cors(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "prod-secret")
    monkeypatch.setenv("ALLOWED_ORIGINS", "*")
    with pytest.raises(RuntimeError, match="ALLOWED_ORIGINS"):
        Settings()


def test_share_url_uses_details_path(monkeypatch):
    monkeypatch.setenv("FRONTEND_URL", "https://transformtoliberation.com")
    from app.core import config as config_mod

    config_mod.settings.FRONTEND_URL = "https://transformtoliberation.com"
    url = public_story_share_url("abc-123")
    assert url == "https://transformtoliberation.com/details/abc-123"
    assert "/stories/" not in url


def test_story_model_declares_publication_columns():
    column_names = set(Story.__table__.columns.keys())
    assert "content_status" in column_names
    assert "cover_status" in column_names
    assert "voice_status" in column_names
    assert "voice_not_required" in column_names
    assert "published_at" in column_names
    assert AssetReviewStatus.ready_for_review.value == "ready_for_review"


def test_refresh_allows_expired_token_with_valid_version():
    from app.api.deps import refresh_access_token

    user = MagicMock()
    user.id = uuid4()
    user.is_active = True
    user.token_version = 3
    token = create_access_token(
        data={"sub": str(user.id)},
        user_token_version=3,
        expires_delta=timedelta(seconds=-10),
    )
    db = MagicMock()
    with patch("app.api.deps.get_user_by_id", return_value=user):
        refreshed = refresh_access_token(db, token)
    payload = jwt.decode(
        refreshed,
        options={"verify_signature": False, "verify_exp": False},
    )
    assert payload["sub"] == str(user.id)
    assert payload["exp"] > datetime.now(timezone.utc).timestamp()


def test_refresh_rejects_revoked_token():
    from app.api.deps import refresh_access_token

    user = MagicMock()
    user.id = uuid4()
    user.is_active = True
    user.token_version = 4
    token = create_access_token(
        data={"sub": str(user.id)},
        user_token_version=3,
        expires_delta=timedelta(minutes=5),
    )
    db = MagicMock()
    with patch("app.api.deps.get_user_by_id", return_value=user):
        with pytest.raises(Exception) as exc:
            refresh_access_token(db, token)
    assert exc.value.status_code == 401


def test_rate_limit_trips_after_max():
    key = f"test-{uuid4()}"
    for _ in range(3):
        enforce_rate_limit(key, max_requests=3, window_seconds=60)
    with pytest.raises(Exception) as exc:
        enforce_rate_limit(key, max_requests=3, window_seconds=60)
    assert exc.value.status_code == 429


def test_checkout_requires_auth():
    from app.main import app

    client = TestClient(app)
    response = client.post("/v1/payment/checkout/start", json={"journey_code": "fear"})
    assert response.status_code == 401


def test_checkout_ignores_client_user_id():
    from app.api.deps import get_current_user
    from app.core.db import get_db
    from app.main import app

    user = MagicMock()
    user.id = uuid4()
    checkout = {
        "payment_id": uuid4(),
        "provider_payment_id": "cs_test",
        "checkout_url": "https://stripe.test/c",
        "checkout_status": "pending",
    }

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: MagicMock()
    try:
        with patch(
            "app.api.v1.endpoints.routes_payment.BillingService.start_checkout",
            return_value=checkout,
        ) as mocked:
            client = TestClient(app)
            other_id = str(uuid4())
            response = client.post(
                "/v1/payment/checkout/start",
                json={"user_id": other_id, "journey_code": "fear"},
            )
            assert response.status_code == 200
            assert mocked.call_args.kwargs["user_id"] == user.id
            assert str(mocked.call_args.kwargs["user_id"]) != other_id
    finally:
        app.dependency_overrides.clear()


def test_payment_history_ignores_path_user_id():
    from app.api.deps import get_current_user
    from app.core.db import get_db
    from app.main import app

    user = MagicMock()
    user.id = uuid4()
    other_id = uuid4()

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: MagicMock()
    try:
        with patch(
            "app.api.v1.endpoints.routes_payment.BillingService.payment_history",
            return_value=[],
        ) as mocked:
            client = TestClient(app)
            response = client.get(f"/v1/payment/history/{other_id}")
            assert response.status_code == 200
            assert mocked.call_args.kwargs["user_id"] == user.id
    finally:
        app.dependency_overrides.clear()
