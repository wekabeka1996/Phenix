"""Test exchange rejection NRR-018 integration."""

import pytest
from unittest.mock import Mock, patch
from vfoundation.adapters.binance_adapter import _make_binance_error


class TestExchangeRejectNRR018:
    """Test exchange rejection returns NRR-018."""

    def test_make_binance_error_logs_nrr_018_for_rejection_codes(self, caplog):
        """Test that _make_binance_error logs NRR-018 for specific rejection codes."""
        import logging
        error_codes = [-1013, -1021, -2010]  # Binance specific rejection codes

        for code in error_codes:
            caplog.clear()
            with caplog.at_level(logging.WARNING, logger='vfoundation.adapters.binance_adapter'):
                resp_mock = Mock()
                resp_mock.status_code = 400
                err = {"code": code, "msg": f"Error {code}"}

                # Call the function
                result = _make_binance_error(resp_mock, err)

                # Verify logging occurred
                assert len(caplog.records) == 1
                log_message = caplog.records[0].message
                assert "nrr_code=NRR-018" in log_message
                assert str(code) in log_message

                # Verify error object
                if isinstance(result, dict):
                    assert result["code"] == code
                    assert result["msg"] == f"Error {code}"
                    assert result["nrr_code"] == "NRR-018"
                else:
                    assert result.code == code
                    assert result.msg == f"Error {code}"

    def test_make_binance_error_does_not_log_nrr_018_for_other_codes(self):
        """Test that _make_binance_error doesn't log NRR-018 for non-rejection codes."""
        other_codes = [-1001, -1002, -2011]  # Other Binance error codes

        for code in other_codes:
            with patch('vfoundation.adapters.binance_adapter.log') as mock_log:
                resp_mock = Mock()
                resp_mock.status_code = 400
                err = {"code": code, "msg": f"Error {code}"}

                # Call the function
                result = _make_binance_error(resp_mock, err)

                # Verify no NRR-018 logging for other codes
                if mock_log.warning.called:
                    call_args = mock_log.warning.call_args[0]
                    # Format the message
                    message = call_args[0] % call_args[1:]
                    assert "nrr_code=NRR-018" not in message

                # Verify error object still created
                if isinstance(result, dict):
                    assert result["code"] == code
                    assert result["msg"] == f"Error {code}"
                else:
                    assert result.code == code

    def test_nrr_018_code_exists(self):
        """Test that NRR-018 code is defined."""
        from vfoundation.core.why_codes import WhyCode

        assert hasattr(WhyCode, 'NRR_018_EXCHANGE_REJECTED_ORDER')
        code = WhyCode.NRR_018_EXCHANGE_REJECTED_ORDER
        assert code.value == "NRR-018"
