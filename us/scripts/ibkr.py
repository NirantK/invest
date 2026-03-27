#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["ib-async", "typer", "rich", "python-dotenv"]
# ///
"""
Interactive Brokers CLI

Query portfolio positions, account balances, and real-time quotes.
Requires TWS or IB Gateway running with API enabled.
"""

import os
import json
import sys
from enum import Enum
from typing import Optional

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Interactive Brokers CLI")
console = Console()

# Load .env from common locations
for env_path in [".env", os.path.expanduser("~/.env")]:
    if os.path.exists(env_path):
        load_dotenv(env_path)
        break

DEFAULT_PORT = int(os.getenv("IBKR_PORT", "4001"))
DEFAULT_CLIENT_ID = int(os.getenv("IBKR_CLIENT_ID", "1"))


class OutputFormat(str, Enum):
    table = "table"
    json = "json"


def get_ib(port: int, client_id: int):
    """Connect to IBKR and return IB instance."""
    from ib_async import IB

    ib = IB()
    try:
        ib.connect("127.0.0.1", port, clientId=client_id)
    except ConnectionRefusedError:
        console.print("[red]Error: Cannot connect to IBKR[/red]")
        console.print(f"Ensure IB Gateway/TWS is running on port {port}")
        console.print("Enable API: Configure → Settings → API → Enable ActiveX and Socket Clients")
        sys.exit(1)
    return ib


def format_currency(amount: float) -> str:
    """Format amount as currency."""
    if amount >= 0:
        return f"${amount:,.2f}"
    return f"-${abs(amount):,.2f}"


def format_pct(value: float) -> str:
    """Format as percentage with color hint."""
    return f"{value:+.2f}%"


@app.command()
def positions(
    port: int = typer.Option(DEFAULT_PORT, "--port", "-p", help="IBKR port"),
    client_id: int = typer.Option(DEFAULT_CLIENT_ID, "--client-id", "-c", help="Client ID"),
    fmt: OutputFormat = typer.Option(OutputFormat.table, "--format", "-f", help="Output format"),
):
    """List all portfolio positions with P&L and returns."""
    from ib_async import Stock, util

    ib = get_ib(port, client_id)

    try:
        positions_list = ib.positions()

        if not positions_list:
            console.print("[yellow]No positions found[/yellow]")
            return

        # Fetch real-time prices for all positions
        ib.reqMarketDataType(3)  # Delayed data
        contracts = []
        for p in positions_list:
            contract = Stock(p.contract.symbol, "SMART", "USD")
            ib.qualifyContracts(contract)
            contracts.append((p, contract, ib.reqMktData(contract)))

        util.sleep(2)  # Wait for data

        # Build position data with P&L
        position_data = []
        total_cost = 0
        total_value = 0

        for p, contract, ticker in contracts:
            qty = float(p.position)
            avg_cost = float(p.avgCost)
            cost_basis = qty * avg_cost

            # Get current price (try last, then close, then bid)
            current_price = None
            for price in [ticker.last, ticker.close, ticker.bid]:
                if price and price > 0 and not (isinstance(price, float) and price != price):
                    current_price = price
                    break

            if current_price:
                market_value = qty * current_price
                pnl = market_value - cost_basis
                pnl_pct = (pnl / cost_basis) * 100 if cost_basis > 0 else 0
            else:
                market_value = cost_basis  # Fallback
                pnl = 0
                pnl_pct = 0
                current_price = avg_cost

            total_cost += cost_basis
            total_value += market_value

            position_data.append({
                "symbol": p.contract.symbol,
                "secType": p.contract.secType,
                "qty": qty,
                "avgCost": avg_cost,
                "currentPrice": current_price,
                "costBasis": cost_basis,
                "marketValue": market_value,
                "pnl": pnl,
                "pnlPct": pnl_pct,
                "account": p.account,
            })

        if fmt == OutputFormat.json:
            console.print_json(json.dumps(position_data, indent=2))
            return

        table = Table(title="Portfolio Positions")
        table.add_column("Symbol", style="cyan")
        table.add_column("Qty", justify="right")
        table.add_column("Avg Cost", justify="right")
        table.add_column("Price", justify="right")
        table.add_column("Value", justify="right")
        table.add_column("P&L", justify="right")
        table.add_column("Return", justify="right")

        for d in position_data:
            pnl_style = "green" if d["pnl"] >= 0 else "red"
            pnl_str = f"+${d['pnl']:.2f}" if d["pnl"] >= 0 else f"-${abs(d['pnl']):.2f}"
            pct_str = f"+{d['pnlPct']:.1f}%" if d["pnlPct"] >= 0 else f"{d['pnlPct']:.1f}%"

            table.add_row(
                d["symbol"],
                f"{d['qty']:,.2f}",
                format_currency(d["avgCost"]),
                format_currency(d["currentPrice"]),
                format_currency(d["marketValue"]),
                f"[{pnl_style}]{pnl_str}[/{pnl_style}]",
                f"[{pnl_style}]{pct_str}[/{pnl_style}]",
            )

        # Add totals row
        total_pnl = total_value - total_cost
        total_pct = (total_pnl / total_cost) * 100 if total_cost > 0 else 0
        pnl_style = "green" if total_pnl >= 0 else "red"
        pnl_str = f"+${total_pnl:.2f}" if total_pnl >= 0 else f"-${abs(total_pnl):.2f}"
        pct_str = f"+{total_pct:.1f}%" if total_pct >= 0 else f"{total_pct:.1f}%"

        table.add_row(
            "[bold]TOTAL[/bold]", "", "", "",
            f"[bold]{format_currency(total_value)}[/bold]",
            f"[bold {pnl_style}]{pnl_str}[/bold {pnl_style}]",
            f"[bold {pnl_style}]{pct_str}[/bold {pnl_style}]",
        )

        console.print(table)
    finally:
        ib.disconnect()


@app.command()
def account(
    port: int = typer.Option(DEFAULT_PORT, "--port", "-p", help="IBKR port"),
    client_id: int = typer.Option(DEFAULT_CLIENT_ID, "--client-id", "-c", help="Client ID"),
    fmt: OutputFormat = typer.Option(OutputFormat.table, "--format", "-f", help="Output format"),
):
    """Show account summary (cash, equity, margin)."""
    ib = get_ib(port, client_id)

    try:
        summary = ib.accountSummary()

        # Group by tag
        data = {}
        for item in summary:
            data[item.tag] = {
                "value": item.value,
                "currency": item.currency,
                "account": item.account,
            }

        if fmt == OutputFormat.json:
            console.print_json(json.dumps(data, indent=2))
            return

        # Key metrics to display
        key_tags = [
            "NetLiquidation",
            "TotalCashValue",
            "GrossPositionValue",
            "MaintMarginReq",
            "AvailableFunds",
            "BuyingPower",
            "Leverage",
        ]

        table = Table(title="Account Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green", justify="right")
        table.add_column("Currency", style="dim")

        for tag in key_tags:
            if tag in data:
                val = data[tag]["value"]
                try:
                    val_float = float(val)
                    if tag == "Leverage":
                        display = f"{val_float:.2f}x"
                    else:
                        display = format_currency(val_float)
                except ValueError:
                    display = val
                table.add_row(tag, display, data[tag]["currency"])

        console.print(table)
    finally:
        ib.disconnect()


@app.command()
def value(
    port: int = typer.Option(DEFAULT_PORT, "--port", "-p", help="IBKR port"),
    client_id: int = typer.Option(DEFAULT_CLIENT_ID, "--client-id", "-c", help="Client ID"),
    fmt: OutputFormat = typer.Option(OutputFormat.table, "--format", "-f", help="Output format"),
):
    """Portfolio value breakdown."""
    ib = get_ib(port, client_id)

    try:
        summary = ib.accountSummary()

        result = {}
        for item in summary:
            if item.tag in ("NetLiquidation", "TotalCashValue", "GrossPositionValue"):
                result[item.tag] = float(item.value)

        if fmt == OutputFormat.json:
            console.print_json(json.dumps(result, indent=2))
            return

        console.print("\n[bold cyan]Portfolio Value[/bold cyan]\n")

        table = Table(show_header=False, box=None)
        table.add_column("Metric", style="white")
        table.add_column("Value", style="green", justify="right")

        table.add_row("Net Liquidation", format_currency(result.get("NetLiquidation", 0)))
        table.add_row("Cash", format_currency(result.get("TotalCashValue", 0)))
        table.add_row("Positions", format_currency(result.get("GrossPositionValue", 0)))

        console.print(table)
    finally:
        ib.disconnect()


@app.command()
def quote(
    symbol: str = typer.Argument(..., help="Stock symbol (e.g., AAPL)"),
    port: int = typer.Option(DEFAULT_PORT, "--port", "-p", help="IBKR port"),
    client_id: int = typer.Option(DEFAULT_CLIENT_ID, "--client-id", "-c", help="Client ID"),
    fmt: OutputFormat = typer.Option(OutputFormat.table, "--format", "-f", help="Output format"),
):
    """Get real-time quote for a stock."""
    from ib_async import Stock, util

    ib = get_ib(port, client_id)

    try:
        contract = Stock(symbol.upper(), "SMART", "USD")
        ib.qualifyContracts(contract)
        ticker = ib.reqMktData(contract)
        util.sleep(2)  # Wait for data

        data = {
            "symbol": symbol.upper(),
            "bid": ticker.bid if ticker.bid > 0 else None,
            "ask": ticker.ask if ticker.ask > 0 else None,
            "last": ticker.last if ticker.last > 0 else None,
            "volume": ticker.volume if ticker.volume > 0 else None,
            "high": ticker.high if ticker.high > 0 else None,
            "low": ticker.low if ticker.low > 0 else None,
            "close": ticker.close if ticker.close > 0 else None,
        }

        if fmt == OutputFormat.json:
            console.print_json(json.dumps(data, indent=2))
            return

        console.print(f"\n[bold cyan]{symbol.upper()}[/bold cyan]\n")

        table = Table(show_header=False, box=None)
        table.add_column("Field", style="dim")
        table.add_column("Value", style="green", justify="right")

        if data["last"]:
            table.add_row("Last", format_currency(data["last"]))
        if data["bid"] and data["ask"]:
            table.add_row("Bid/Ask", f"{format_currency(data['bid'])} / {format_currency(data['ask'])}")
        if data["high"] and data["low"]:
            table.add_row("High/Low", f"{format_currency(data['high'])} / {format_currency(data['low'])}")
        if data["close"]:
            table.add_row("Prev Close", format_currency(data["close"]))
        if data["volume"]:
            table.add_row("Volume", f"{data['volume']:,.0f}")

        console.print(table)
    finally:
        ib.disconnect()


@app.command()
def quotes(
    symbols: list[str] = typer.Argument(..., help="Stock symbols (e.g., AAPL MSFT GOOGL)"),
    port: int = typer.Option(DEFAULT_PORT, "--port", "-p", help="IBKR port"),
    client_id: int = typer.Option(DEFAULT_CLIENT_ID, "--client-id", "-c", help="Client ID"),
    fmt: OutputFormat = typer.Option(OutputFormat.table, "--format", "-f", help="Output format"),
):
    """Get quotes for multiple symbols."""
    from ib_async import Stock, util

    ib = get_ib(port, client_id)

    try:
        contracts = [Stock(s.upper(), "SMART", "USD") for s in symbols]
        ib.qualifyContracts(*contracts)

        tickers = []
        for contract in contracts:
            tickers.append(ib.reqMktData(contract))

        util.sleep(2)  # Wait for data

        data = []
        for i, ticker in enumerate(tickers):
            data.append({
                "symbol": symbols[i].upper(),
                "last": ticker.last if ticker.last > 0 else None,
                "bid": ticker.bid if ticker.bid > 0 else None,
                "ask": ticker.ask if ticker.ask > 0 else None,
                "volume": ticker.volume if ticker.volume > 0 else None,
            })

        if fmt == OutputFormat.json:
            console.print_json(json.dumps(data, indent=2))
            return

        table = Table(title="Quotes")
        table.add_column("Symbol", style="cyan")
        table.add_column("Last", style="green", justify="right")
        table.add_column("Bid", justify="right")
        table.add_column("Ask", justify="right")
        table.add_column("Volume", justify="right")

        for d in data:
            table.add_row(
                d["symbol"],
                format_currency(d["last"]) if d["last"] else "-",
                format_currency(d["bid"]) if d["bid"] else "-",
                format_currency(d["ask"]) if d["ask"] else "-",
                f"{d['volume']:,.0f}" if d["volume"] else "-",
            )

        console.print(table)
    finally:
        ib.disconnect()


@app.command()
def orders(
    port: int = typer.Option(DEFAULT_PORT, "--port", "-p", help="IBKR port"),
    client_id: int = typer.Option(DEFAULT_CLIENT_ID, "--client-id", "-c", help="Client ID"),
    fmt: OutputFormat = typer.Option(OutputFormat.table, "--format", "-f", help="Output format"),
):
    """List all open orders."""
    ib = get_ib(port, client_id)

    try:
        open_trades = ib.openTrades()

        if fmt == OutputFormat.json:
            data = [
                {
                    "orderId": t.order.orderId,
                    "symbol": t.contract.symbol,
                    "action": t.order.action,
                    "quantity": float(t.order.totalQuantity),
                    "orderType": t.order.orderType,
                    "limitPrice": float(t.order.lmtPrice) if t.order.lmtPrice else None,
                    "status": t.orderStatus.status,
                }
                for t in open_trades
            ]
            console.print_json(json.dumps(data, indent=2))
            return

        if not open_trades:
            console.print("[yellow]No open orders[/yellow]")
            return

        table = Table(title="Open Orders")
        table.add_column("Order ID", style="cyan")
        table.add_column("Symbol", style="white")
        table.add_column("Action", style="white")
        table.add_column("Qty", justify="right")
        table.add_column("Type", style="dim")
        table.add_column("Limit", justify="right")
        table.add_column("Status", style="dim")

        for t in open_trades:
            limit_str = format_currency(t.order.lmtPrice) if t.order.lmtPrice else "-"
            table.add_row(
                str(t.order.orderId),
                t.contract.symbol,
                t.order.action,
                f"{t.order.totalQuantity:,.0f}",
                t.order.orderType,
                limit_str,
                t.orderStatus.status,
            )

        console.print(table)
    finally:
        ib.disconnect()


@app.command()
def cancel(
    order_id: Optional[int] = typer.Argument(None, help="Order ID to cancel (from 'orders' command)"),
    symbol: Optional[str] = typer.Option(None, "--symbol", "-s", help="Cancel all orders for this symbol"),
    all_orders: bool = typer.Option(False, "--all", "-a", help="Cancel ALL open orders"),
    port: int = typer.Option(DEFAULT_PORT, "--port", "-p", help="IBKR port"),
    client_id: int = typer.Option(DEFAULT_CLIENT_ID, "--client-id", "-c", help="Client ID"),
    force: bool = typer.Option(False, "--force", "-y", help="Skip confirmation prompt"),
):
    """Cancel open orders by ID, symbol, or all."""
    ib = get_ib(port, client_id)

    try:
        open_trades = ib.openTrades()

        if not open_trades:
            console.print("[yellow]No open orders to cancel[/yellow]")
            return

        # Determine which trades to cancel
        to_cancel = []

        if all_orders:
            to_cancel = open_trades
        elif symbol:
            to_cancel = [t for t in open_trades if t.contract.symbol.upper() == symbol.upper()]
            if not to_cancel:
                console.print(f"[yellow]No open orders found for {symbol.upper()}[/yellow]")
                return
        elif order_id:
            to_cancel = [t for t in open_trades if t.order.orderId == order_id]
            if not to_cancel:
                console.print(f"[yellow]Order ID {order_id} not found[/yellow]")
                console.print("[dim]Use 'orders' command to see open orders[/dim]")
                return
        else:
            console.print("[red]Error: Specify order_id, --symbol, or --all[/red]")
            console.print("[dim]Examples:[/dim]")
            console.print("[dim]  cancel 123          # Cancel order ID 123[/dim]")
            console.print("[dim]  cancel -s VALE      # Cancel all VALE orders[/dim]")
            console.print("[dim]  cancel --all        # Cancel ALL orders[/dim]")
            return

        # Show what will be cancelled
        console.print(f"\n[bold yellow]Orders to cancel ({len(to_cancel)}):[/bold yellow]\n")

        table = Table(show_header=True)
        table.add_column("Order ID", style="cyan")
        table.add_column("Symbol")
        table.add_column("Action")
        table.add_column("Qty", justify="right")
        table.add_column("Type")
        table.add_column("Limit", justify="right")

        for t in to_cancel:
            limit_str = format_currency(t.order.lmtPrice) if t.order.lmtPrice else "-"
            table.add_row(
                str(t.order.orderId),
                t.contract.symbol,
                t.order.action,
                f"{t.order.totalQuantity:,.0f}",
                t.order.orderType,
                limit_str,
            )

        console.print(table)

        # Confirmation
        if not force:
            confirm = typer.confirm("\nCancel these orders?")
            if not confirm:
                console.print("[dim]Aborted - no orders modified[/dim]")
                return

        # Cancel orders
        cancelled = 0
        for trade in to_cancel:
            ib.cancelOrder(trade.order)
            cancelled += 1

        console.print(f"\n[green]✓ Cancelled {cancelled} order(s)[/green]")

    finally:
        ib.disconnect()


@app.command()
def buy(
    symbol: str = typer.Argument(..., help="Stock symbol (e.g., PPLT)"),
    amount: float = typer.Argument(..., help="Dollar amount to invest"),
    port: int = typer.Option(DEFAULT_PORT, "--port", "-p", help="IBKR port"),
    client_id: int = typer.Option(DEFAULT_CLIENT_ID, "--client-id", "-c", help="Client ID"),
    dry_run: bool = typer.Option(True, "--dry-run/--execute", help="Dry run (default) or execute"),
    limit_price: Optional[float] = typer.Option(None, "--limit", "-l", help="Limit price (uses market if not set)"),
):
    """Buy shares of a stock with a dollar amount (market or limit order)."""
    from ib_async import Stock, MarketOrder, LimitOrder, util

    ib = get_ib(port, client_id)

    try:
        contract = Stock(symbol.upper(), "SMART", "USD")
        ib.qualifyContracts(contract)

        # Use limit price if provided, otherwise get market data
        if limit_price:
            price = limit_price
            order_type = "LIMIT"
        else:
            ib.reqMarketDataType(3)  # 3 = delayed data
            ticker = ib.reqMktData(contract)
            util.sleep(3)

            # Try ask, then last, then close
            price = None
            for p in [ticker.ask, ticker.last, ticker.close]:
                if p and p > 0 and not (isinstance(p, float) and p != p):  # not NaN
                    price = p
                    break
            if not price:
                console.print(f"[red]Error: Could not get price for {symbol}[/red]")
                console.print(f"[dim]Ticker data: ask={ticker.ask}, last={ticker.last}, close={ticker.close}[/dim]")
                console.print(f"[dim]Use --limit PRICE to specify a limit price[/dim]")
                return
            order_type = "MARKET"

        # Calculate shares (whole shares only via API)
        shares = int(amount / price)
        if shares < 1:
            console.print(f"[red]Error: ${amount:.2f} not enough for 1 share at ${price:.2f}[/red]")
            return

        total_cost = shares * price
        remainder = amount - total_cost

        console.print(f"\n[bold cyan]Order: {symbol.upper()}[/bold cyan]\n")
        console.print(f"  Price:     ${price:.2f}")
        console.print(f"  Shares:    {shares}")
        console.print(f"  Total:     ${total_cost:.2f}")
        if remainder > 0:
            console.print(f"  Remainder: ${remainder:.2f} (fractional not supported via API)")

        if dry_run:
            console.print(f"\n[yellow]DRY RUN - No order placed[/yellow]")
            console.print(f"[dim]Use --execute to place the order[/dim]")
            return

        # Place order (limit or market)
        if limit_price:
            order = LimitOrder("BUY", shares, limit_price)
        else:
            order = MarketOrder("BUY", shares)
        trade = ib.placeOrder(contract, order)
        util.sleep(1)

        console.print(f"\n[green]Order placed![/green]")
        console.print(f"  Order ID: {trade.order.orderId}")
        console.print(f"  Status:   {trade.orderStatus.status}")

    finally:
        ib.disconnect()


@app.command()
def sell(
    symbol: str = typer.Argument(..., help="Stock symbol (e.g., VALE)"),
    shares: Optional[int] = typer.Option(None, "--shares", "-n", help="Number of shares (default: all)"),
    amount: Optional[float] = typer.Option(None, "--amount", "-a", help="Dollar amount to sell"),
    port: int = typer.Option(DEFAULT_PORT, "--port", "-p", help="IBKR port"),
    client_id: int = typer.Option(DEFAULT_CLIENT_ID, "--client-id", "-c", help="Client ID"),
    dry_run: bool = typer.Option(True, "--dry-run/--execute", help="Dry run (default) or execute"),
    limit_price: Optional[float] = typer.Option(None, "--limit", "-l", help="Limit price (uses market if not set)"),
):
    """Sell shares of a stock (by shares, amount, or all)."""
    from ib_async import Stock, MarketOrder, LimitOrder, util

    ib = get_ib(port, client_id)

    try:
        contract = Stock(symbol.upper(), "SMART", "USD")
        ib.qualifyContracts(contract)

        # Get current position
        positions_list = ib.positions()
        position = None
        for p in positions_list:
            if p.contract.symbol.upper() == symbol.upper():
                position = p
                break

        if not position or float(position.position) <= 0:
            console.print(f"[red]Error: No position found for {symbol.upper()}[/red]")
            return

        current_shares = int(float(position.position))
        avg_cost = float(position.avgCost)

        # Get current price
        if limit_price:
            price = limit_price
            order_type = "LIMIT"
        else:
            ib.reqMarketDataType(3)
            ticker = ib.reqMktData(contract)
            util.sleep(3)

            price = None
            for p in [ticker.bid, ticker.last, ticker.close]:
                if p and p > 0 and not (isinstance(p, float) and p != p):
                    price = p
                    break
            if not price:
                console.print(f"[red]Error: Could not get price for {symbol}[/red]")
                console.print(f"[dim]Use --limit PRICE to specify a limit price[/dim]")
                return
            order_type = "MARKET"

        # Determine shares to sell
        if shares:
            sell_shares = min(shares, current_shares)
        elif amount:
            sell_shares = min(int(amount / price), current_shares)
        else:
            sell_shares = current_shares  # Sell all

        if sell_shares < 1:
            console.print(f"[red]Error: Cannot sell less than 1 share[/red]")
            return

        total_value = sell_shares * price
        gain_loss = (price - avg_cost) * sell_shares
        gain_pct = ((price / avg_cost) - 1) * 100 if avg_cost > 0 else 0

        console.print(f"\n[bold cyan]Sell Order: {symbol.upper()}[/bold cyan]\n")
        console.print(f"  Position:  {current_shares} shares @ ${avg_cost:.2f} avg")
        console.print(f"  Selling:   {sell_shares} shares")
        console.print(f"  Price:     ${price:.2f} ({order_type})")
        console.print(f"  Proceeds:  ${total_value:.2f}")

        if gain_loss >= 0:
            console.print(f"  Gain:      [green]+${gain_loss:.2f} ({gain_pct:+.1f}%)[/green]")
        else:
            console.print(f"  Loss:      [red]-${abs(gain_loss):.2f} ({gain_pct:+.1f}%)[/red]")

        if sell_shares < current_shares:
            remaining = current_shares - sell_shares
            console.print(f"  Remaining: {remaining} shares")

        if dry_run:
            console.print(f"\n[yellow]DRY RUN - No order placed[/yellow]")
            console.print(f"[dim]Use --execute to place the order[/dim]")
            return

        # Place order
        if limit_price:
            order = LimitOrder("SELL", sell_shares, limit_price)
        else:
            order = MarketOrder("SELL", sell_shares)
        trade = ib.placeOrder(contract, order)
        util.sleep(1)

        console.print(f"\n[green]Order placed![/green]")
        console.print(f"  Order ID: {trade.order.orderId}")
        console.print(f"  Status:   {trade.orderStatus.status}")

    finally:
        ib.disconnect()


@app.command()
def trades(
    symbol: Optional[str] = typer.Argument(None, help="Filter by symbol"),
    port: int = typer.Option(DEFAULT_PORT, "--port", "-p", help="IBKR port"),
    client_id: int = typer.Option(DEFAULT_CLIENT_ID, "--client-id", "-c", help="Client ID"),
    fmt: OutputFormat = typer.Option(OutputFormat.table, "--format", "-f", help="Output format"),
):
    """Show execution history (current session fills + completed orders)."""
    from ib_async import ExecutionFilter, util

    ib = get_ib(port, client_id)

    filt = ExecutionFilter()
    if symbol:
        filt.symbol = symbol.upper()

    fills = ib.reqExecutions(filt)
    util.sleep(1)

    # Also get completed orders for broader history
    completed = ib.reqCompletedOrders(apiOnly=False)
    util.sleep(1)

    rows = []
    seen_exec_ids = set()

    # Fills from reqExecutions
    for fill in fills:
        e = fill.execution
        seen_exec_ids.add(e.execId)
        cr = fill.commissionReport
        rows.append({
            "time": str(e.time),
            "symbol": fill.contract.symbol,
            "side": e.side,
            "qty": e.shares,
            "price": e.price,
            "avgPrice": e.avgPrice,
            "commission": cr.commission if cr else 0,
            "realizedPNL": cr.realizedPNL if cr and cr.realizedPNL != 1.7976931348623157e+308 else 0,
        })

    # Completed orders (broader history)
    for trade in completed:
        sym = trade.contract.symbol
        if symbol and sym.upper() != symbol.upper():
            continue
        order = trade.order
        status = trade.orderStatus
        if status.filled > 0:
            rows.append({
                "time": str(trade.log[-1].time) if trade.log else "?",
                "symbol": sym,
                "side": order.action,
                "qty": status.filled,
                "price": status.avgFillPrice,
                "avgPrice": status.avgFillPrice,
                "commission": 0,
                "realizedPNL": 0,
            })

    # Deduplicate by (symbol, time, qty)
    unique = []
    seen = set()
    for r in sorted(rows, key=lambda x: x["time"]):
        key = (r["symbol"], r["time"][:16], r["qty"])
        if key not in seen:
            seen.add(key)
            unique.append(r)

    ib.disconnect()

    if fmt == OutputFormat.json:
        console.print(json.dumps(unique, indent=2, default=str))
        return

    if not unique:
        console.print("[yellow]No executions found. IB API only returns current-session fills.[/yellow]")
        console.print("[dim]For full history, use Flex Queries in TWS: Reports > Flex Queries > Trade Confirmation[/dim]")
        return

    table = Table(title="Trade Executions")
    table.add_column("Time", style="dim")
    table.add_column("Symbol", style="bold")
    table.add_column("Side")
    table.add_column("Qty", justify="right")
    table.add_column("Price", justify="right")
    table.add_column("Commission", justify="right")
    table.add_column("Realized P&L", justify="right")

    for r in unique:
        side_style = "green" if r["side"] in ("BOT", "BUY") else "red"
        pnl = r["realizedPNL"]
        pnl_str = f"${pnl:,.2f}" if pnl else "-"
        pnl_style = "green" if pnl > 0 else ("red" if pnl < 0 else "dim")

        table.add_row(
            r["time"][:19],
            r["symbol"],
            f"[{side_style}]{r['side']}[/{side_style}]",
            f"{r['qty']:.2f}",
            f"${r['price']:.2f}",
            f"${r['commission']:.2f}" if r["commission"] else "-",
            f"[{pnl_style}]{pnl_str}[/{pnl_style}]",
        )

    console.print(table)


@app.command()
def chain(
    symbol: str = typer.Argument(..., help="Stock symbol (e.g., INTC)"),
    expiry: Optional[str] = typer.Option(None, "--expiry", "-e", help="Filter by expiry (YYYYMMDD)"),
    right: Optional[str] = typer.Option(None, "--right", "-r", help="CALL or PUT"),
    port: int = typer.Option(DEFAULT_PORT, "--port", "-p", help="IBKR port"),
    client_id: int = typer.Option(DEFAULT_CLIENT_ID, "--client-id", "-c", help="Client ID"),
    fmt: OutputFormat = typer.Option(OutputFormat.table, "--format", "-f", help="Output format"),
):
    """Show options chain for a symbol (available expirations and strikes)."""
    from ib_async import Stock, util

    ib = get_ib(port, client_id)

    contract = Stock(symbol.upper(), "SMART", "USD")
    ib.qualifyContracts(contract)

    chains = ib.reqSecDefOptParams(
        contract.symbol, "", contract.secType, contract.conId
    )
    util.sleep(1)

    if not chains:
        console.print(f"[yellow]No options chain found for {symbol.upper()}[/yellow]")
        ib.disconnect()
        return

    # Use SMART exchange chain
    opt_chain = None
    for c in chains:
        if c.exchange == "SMART":
            opt_chain = c
            break
    if not opt_chain:
        opt_chain = chains[0]

    expirations = sorted(opt_chain.expirations)
    strikes = sorted(opt_chain.strikes)

    if expiry:
        expirations = [e for e in expirations if e == expiry]

    ib.disconnect()

    if fmt == OutputFormat.json:
        console.print(json.dumps({
            "symbol": symbol.upper(),
            "exchange": opt_chain.exchange,
            "expirations": expirations,
            "strikes": [float(s) for s in strikes],
            "multiplier": opt_chain.multiplier,
        }, indent=2))
        return

    console.print(f"\n[bold cyan]Options Chain: {symbol.upper()}[/bold cyan]")
    console.print(f"  Exchange:   {opt_chain.exchange}")
    console.print(f"  Multiplier: {opt_chain.multiplier}")

    table = Table(title="Available Expirations")
    table.add_column("Expiry", style="bold")
    table.add_column("Days Out", justify="right")

    from datetime import datetime, date
    today = date.today()
    for exp in expirations[:20]:
        exp_date = datetime.strptime(exp, "%Y%m%d").date()
        days = (exp_date - today).days
        table.add_row(exp, str(days))

    console.print(table)

    # Show strikes near current price
    ib2 = get_ib(port, client_id + 10)
    contract2 = Stock(symbol.upper(), "SMART", "USD")
    ib2.qualifyContracts(contract2)
    ib2.reqMarketDataType(3)
    ticker = ib2.reqMktData(contract2)
    util.sleep(3)

    price = None
    for p in [ticker.last, ticker.close, ticker.ask]:
        if p and p > 0 and not (isinstance(p, float) and p != p):
            price = p
            break
    ib2.disconnect()

    if price:
        console.print(f"\n  Current price: ${price:.2f}")
        nearby = [s for s in strikes if abs(s - price) / price < 0.30]
        console.print(f"  Strikes near price (±30%): {', '.join(f'${s:.0f}' for s in nearby[:25])}")


@app.command()
def buy_option(
    symbol: str = typer.Argument(..., help="Stock symbol (e.g., INTC)"),
    amount: float = typer.Argument(..., help="Dollar amount to spend on premium"),
    expiry: str = typer.Option(..., "--expiry", "-e", help="Expiration date (YYYYMMDD)"),
    strike: float = typer.Option(..., "--strike", "-s", help="Strike price"),
    right: str = typer.Option("CALL", "--right", "-r", help="CALL or PUT"),
    port: int = typer.Option(DEFAULT_PORT, "--port", "-p", help="IBKR port"),
    client_id: int = typer.Option(DEFAULT_CLIENT_ID, "--client-id", "-c", help="Client ID"),
    dry_run: bool = typer.Option(True, "--dry-run/--execute", help="Dry run (default) or execute"),
    limit_price: Optional[float] = typer.Option(None, "--limit", "-l", help="Limit price per contract (uses market if not set)"),
):
    """Buy options contracts with a dollar amount."""
    from ib_async import Option, MarketOrder, LimitOrder, util

    ib = get_ib(port, client_id)

    right = right.upper()
    if right not in ("CALL", "PUT"):
        console.print("[red]Error: --right must be CALL or PUT[/red]")
        ib.disconnect()
        raise typer.Exit(1)

    contract = Option(symbol.upper(), expiry, strike, right, "SMART")
    ib.qualifyContracts(contract)

    if limit_price:
        price = limit_price
        order_type = "LIMIT"
    else:
        ib.reqMarketDataType(3)
        ticker = ib.reqMktData(contract)
        util.sleep(3)

        price = None
        for p in [ticker.ask, ticker.last, ticker.close]:
            if p and p > 0 and not (isinstance(p, float) and p != p):
                price = p
                break

        if not price:
            console.print(f"[red]Error: Could not get price for {symbol.upper()} {right} ${strike} {expiry}[/red]")
            console.print(f"Ticker data: ask={ticker.ask}, last={ticker.last}, close={ticker.close}")
            console.print(f"[dim]Use --limit PRICE to specify a limit price[/dim]")
            ib.disconnect()
            raise typer.Exit(1)
        order_type = "MARKET"

    # Options multiplier is 100
    cost_per_contract = price * 100
    num_contracts = max(1, int(amount / cost_per_contract))
    total_cost = num_contracts * cost_per_contract

    console.print(f"\n[bold cyan]Options Order: {symbol.upper()} {right} ${strike} exp {expiry}[/bold cyan]\n")
    console.print(f"  Premium:    ${price:.2f} per share ({order_type})")
    console.print(f"  Contracts:  {num_contracts} (× 100 shares each)")
    console.print(f"  Total cost: ${total_cost:,.2f}")
    console.print(f"  Budget:     ${amount:,.2f}")

    if total_cost > amount * 1.5:
        console.print(f"\n[yellow]Warning: Total cost (${total_cost:,.2f}) exceeds budget (${amount:,.2f}) significantly[/yellow]")

    if dry_run:
        console.print(f"\n[yellow]DRY RUN - No order placed[/yellow]")
        console.print(f"[dim]Use --execute to place the order[/dim]")
        ib.disconnect()
        return

    if limit_price:
        order = LimitOrder("BUY", num_contracts, limit_price)
    else:
        order = MarketOrder("BUY", num_contracts)
    trade = ib.placeOrder(contract, order)
    util.sleep(1)

    console.print(f"\n[green]Order placed![/green]")
    console.print(f"  Order ID: {trade.order.orderId}")
    console.print(f"  Status:   {trade.orderStatus.status}")

    ib.disconnect()


@app.command()
def sell_option(
    symbol: str = typer.Argument(..., help="Stock symbol (e.g., INTC)"),
    expiry: str = typer.Option(..., "--expiry", "-e", help="Expiration date (YYYYMMDD)"),
    strike: float = typer.Option(..., "--strike", "-s", help="Strike price"),
    right: str = typer.Option("CALL", "--right", "-r", help="CALL or PUT"),
    contracts: Optional[int] = typer.Option(None, "--contracts", "-n", help="Number of contracts (default: all)"),
    port: int = typer.Option(DEFAULT_PORT, "--port", "-p", help="IBKR port"),
    client_id: int = typer.Option(DEFAULT_CLIENT_ID, "--client-id", "-c", help="Client ID"),
    dry_run: bool = typer.Option(True, "--dry-run/--execute", help="Dry run (default) or execute"),
    limit_price: Optional[float] = typer.Option(None, "--limit", "-l", help="Limit price per contract"),
):
    """Sell (close) options positions."""
    from ib_async import Option, MarketOrder, LimitOrder, util

    ib = get_ib(port, client_id)

    right = right.upper()
    contract = Option(symbol.upper(), expiry, strike, right, "SMART")
    ib.qualifyContracts(contract)

    # Find current position
    positions = ib.positions()
    current_qty = 0
    avg_cost = 0
    for pos in positions:
        if (pos.contract.symbol == symbol.upper()
            and pos.contract.secType == "OPT"
            and pos.contract.lastTradeDateOrContractMonth == expiry
            and pos.contract.strike == strike
            and pos.contract.right == right[0]):
            current_qty = int(pos.position)
            avg_cost = pos.avgCost / 100  # Per-share cost
            break

    if current_qty <= 0:
        console.print(f"[yellow]No {right} position found for {symbol.upper()} ${strike} {expiry}[/yellow]")
        ib.disconnect()
        return

    sell_qty = contracts if contracts else current_qty

    if limit_price:
        price = limit_price
        order_type = "LIMIT"
    else:
        ib.reqMarketDataType(3)
        ticker = ib.reqMktData(contract)
        util.sleep(3)

        price = None
        for p in [ticker.bid, ticker.last, ticker.close]:
            if p and p > 0 and not (isinstance(p, float) and p != p):
                price = p
                break

        if not price:
            console.print(f"[red]Error: Could not get price[/red]")
            console.print(f"[dim]Use --limit PRICE to specify a limit price[/dim]")
            ib.disconnect()
            raise typer.Exit(1)
        order_type = "MARKET"

    proceeds = sell_qty * price * 100
    cost_basis = sell_qty * avg_cost * 100
    gain = proceeds - cost_basis
    gain_pct = (price / avg_cost - 1) * 100 if avg_cost > 0 else 0

    console.print(f"\n[bold cyan]Sell Options: {symbol.upper()} {right} ${strike} exp {expiry}[/bold cyan]\n")
    console.print(f"  Position:  {current_qty} contracts @ ${avg_cost:.2f} avg")
    console.print(f"  Selling:   {sell_qty} contracts")
    console.print(f"  Price:     ${price:.2f} ({order_type})")
    console.print(f"  Proceeds:  ${proceeds:,.2f}")

    if gain >= 0:
        console.print(f"  Gain:      [green]+${gain:,.2f} ({gain_pct:+.1f}%)[/green]")
    else:
        console.print(f"  Loss:      [red]-${abs(gain):,.2f} ({gain_pct:+.1f}%)[/red]")

    if dry_run:
        console.print(f"\n[yellow]DRY RUN - No order placed[/yellow]")
        console.print(f"[dim]Use --execute to place the order[/dim]")
        ib.disconnect()
        return

    if limit_price:
        order = LimitOrder("SELL", sell_qty, limit_price)
    else:
        order = MarketOrder("SELL", sell_qty)
    trade = ib.placeOrder(contract, order)
    util.sleep(1)

    console.print(f"\n[green]Order placed![/green]")
    console.print(f"  Order ID: {trade.order.orderId}")
    console.print(f"  Status:   {trade.orderStatus.status}")

    ib.disconnect()


if __name__ == "__main__":
    app()
