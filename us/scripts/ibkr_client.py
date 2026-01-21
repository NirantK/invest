"""
IBKR API client for real-time portfolio data.
Requires TWS or IB Gateway running with API enabled.

Setup:
1. TWS: Edit > Global Configuration > API > Settings
2. Enable "ActiveX and Socket Clients"
3. Port: 7497 (TWS) or 4001 (Gateway)

Library: ib-async (successor to ib_insync)
Docs: https://github.com/ib-api-reloaded/ib_async
"""

import os

from dotenv import load_dotenv
from ib_async import IB, Stock, util

load_dotenv()

DEFAULT_PORT = int(os.getenv("IBKR_PORT", "7497"))
DEFAULT_CLIENT_ID = int(os.getenv("IBKR_CLIENT_ID", "1"))


def connect(host: str = "127.0.0.1", port: int = DEFAULT_PORT, client_id: int = DEFAULT_CLIENT_ID) -> IB:
    """Connect to TWS or IB Gateway."""
    ib = IB()
    ib.connect(host, port, clientId=client_id)
    return ib


def get_portfolio_positions(ib: IB) -> list:
    """Fetch current positions with real-time prices."""
    return ib.positions()


def get_account_summary(ib: IB) -> list:
    """Fetch account value, buying power, etc."""
    return ib.accountSummary()


def get_realtime_quote(ib: IB, symbol: str) -> dict:
    """Get real-time quote for a US stock."""
    contract = Stock(symbol, "SMART", "USD")
    ib.qualifyContracts(contract)
    ticker = ib.reqMktData(contract)
    util.sleep(2)  # Wait for data
    return {
        "symbol": symbol,
        "bid": ticker.bid,
        "ask": ticker.ask,
        "last": ticker.last,
        "volume": ticker.volume,
    }


def get_portfolio_value(ib: IB) -> dict:
    """Get total portfolio value and cash balance."""
    summary = ib.accountSummary()
    result = {}
    for item in summary:
        if item.tag in ("NetLiquidation", "TotalCashValue", "GrossPositionValue"):
            result[item.tag] = float(item.value)
    return result


def disconnect(ib: IB) -> None:
    """Disconnect from IBKR."""
    ib.disconnect()


if __name__ == "__main__":
    print("IBKR Client - requires TWS or IB Gateway running")
    print(f"Default port: {DEFAULT_PORT}")
    print(f"Default client ID: {DEFAULT_CLIENT_ID}")
    print("\nTo test connection:")
    print("  ib = connect()")
    print("  positions = get_portfolio_positions(ib)")
    print("  disconnect(ib)")
