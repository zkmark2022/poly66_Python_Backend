"""Verify AMM system account constants match data dictionary v1.3 §3.1."""
import uuid
from src.pm_account.domain.constants import AMM_USER_ID, AMM_USERNAME, AMM_EMAIL


class TestAMMConstants:
    def test_amm_user_id_is_valid_uuid(self) -> None:
        parsed = uuid.UUID(AMM_USER_ID)
        assert str(parsed) == AMM_USER_ID

    def test_amm_user_id_value(self) -> None:
        assert AMM_USER_ID == "00000000-0000-4000-a000-000000000001"

    def test_amm_username(self) -> None:
        assert AMM_USERNAME == "amm_market_maker"

    def test_amm_email(self) -> None:
        assert AMM_EMAIL == "amm@system.internal"
