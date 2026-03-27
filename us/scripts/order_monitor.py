#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["ib-async", "rich", "python-dotenv"]
# ///
"""
Order Monitor - Check pending orders and convert to market after timeout.

Runs every 3 hours, converts limit orders to market after 2 checks (6 hours).
"""

import os
import json
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from ib_async import IB, Stock, MarketOrder

# Load .env
for env_path in [".env", os.path.expanduser("~/.env")]:
    if os.path.exists(env_path):
        load_dotenv(env_path)
        break

DEFAULT_PORT = int(os.getenv("IBKR_PORT", "4001"))
DEFAULT_CLIENT_ID = int(os.getenv("IBKR_CLIENT_ID", "2"))  # Different client ID
STATE_FILE = Path(__file__).parent / ".order_monitor_state.json"

console = Console()


def log(msg: str):
    """Print timestamped log message."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S ET")
    console.print(f"[dim]{ts}[/dim] {msg}")


def load_state() -> dict:
    """Load monitoring state from file."""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"checks": {}, "started": None}


def save_state(state: dict):
    """Save monitoring state to file."""
    STATE_FILE.write_text(json.dumps(state, indent=2))


def get_open_orders(ib: IB) -> list:
    """Get list of open limit orders."""
    trades = ib.openTrades()
    return [t for t in trades if t.order.orderType == "LMT"]


def cancel_and_replace_with_market(ib: IB, trade) -> bool:
    """Cancel limit order and place market order."""
    symbol = trade.contract.symbol
    qty = trade.order.totalQuantity
    action = trade.order.action

    log(f"[yellow]Converting {symbol} to market order...[/yellow]")

    # Cancel limit order
    ib.cancelOrder(trade.order)
    ib.sleep(1)

    # Place market order
    contract = Stock(symbol, "SMART", "USD")
    ib.qualifyContracts(contract)
    order = MarketOrder(action, qty)
    new_trade = ib.placeOrder(contract, order)
    ib.sleep(1)

    log(f"[green]✓ {symbol}: Market order placed (ID: {new_trade.order.orderId})[/green]")
    return True


def check_orders():
    """Main check function."""
    log("[bold]Order Monitor Check[/bold]")

    ib = IB()
    try:
        ib.connect("127.0.0.1", DEFAULT_PORT, clientId=DEFAULT_CLIENT_ID)
    except ConnectionRefusedError:
        log("[red]Cannot connect to IBKR. Is Gateway/TWS running?[/red]")
        return

    try:
        state = load_state()
        if not state["started"]:
            state["started"] = datetime.now().isoformat()

        open_orders = get_open_orders(ib)

        if not open_orders:
            log("[green]No pending limit orders. All filled![/green]")
            # Clear state
            save_state({"checks": {}, "started": None})
            return "done"

        log(f"Found {len(open_orders)} pending limit order(s)")

        converted = []
        still_pending = []

        for trade in open_orders:
            symbol = trade.contract.symbol
            order_id = str(trade.order.orderId)

            # Track checks for this order
            if order_id not in state["checks"]:
                state["checks"][order_id] = {"symbol": symbol, "count": 0}

            state["checks"][order_id]["count"] += 1
            check_count = state["checks"][order_id]["count"]

            log(f"  {symbol}: Check #{check_count} (limit ${trade.order.lmtPrice})")

            if check_count >= 2:
                # Convert to market
                cancel_and_replace_with_market(ib, trade)
                converted.append(symbol)
                del state["checks"][order_id]
            else:
                still_pending.append(symbol)

        save_state(state)

        if converted:
            log(f"[green]Converted to market: {', '.join(converted)}[/green]")
        if still_pending:
            log(f"[yellow]Still pending (will convert next check): {', '.join(still_pending)}[/yellow]")

        return "pending" if still_pending else "done"

    finally:
        ib.disconnect()


def run_monitor(interval_hours: int = 3, max_checks: int = 2):
    """Run the monitor loop."""
    log(f"[bold cyan]Starting Order Monitor[/bold cyan]")
    log(f"Check interval: {interval_hours} hours")
    log(f"Convert to market after: {max_checks} checks ({interval_hours * max_checks} hours)")

    check_num = 0
    while True:
        check_num += 1
        log(f"\n[bold]═══ Check #{check_num} ═══[/bold]")

        result = check_orders()

        if result == "done":
            log("[bold green]All orders filled or converted. Monitor complete.[/bold green]")
            break

        # Wait for next check
        next_check = datetime.now().timestamp() + (interval_hours * 3600)
        next_check_str = datetime.fromtimestamp(next_check).strftime("%H:%M:%S ET")
        log(f"Next check at {next_check_str} (in {interval_hours} hours)")

        time.sleep(interval_hours * 3600)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        # Single check mode
        check_orders()
    else:
        # Continuous monitor mode
        run_monitor()
