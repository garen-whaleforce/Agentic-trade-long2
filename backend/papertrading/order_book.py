"""
Paper Trading Order Book.

Manages paper orders and positions.
"""

from datetime import date, datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from pathlib import Path
import json
import csv

from pydantic import BaseModel


class OrderStatus(str, Enum):
    """Order status."""

    PENDING = "pending"  # Waiting for entry
    OPEN = "open"  # Position is open
    CLOSED = "closed"  # Position is closed
    CANCELLED = "cancelled"  # Order was cancelled


class PaperOrder(BaseModel):
    """Paper trading order."""

    order_id: str
    signal_id: str
    symbol: str

    # Dates
    event_date: date  # T day
    entry_date: date  # T+1 close
    exit_date: date  # T+30 close

    # Signal info
    score: float
    confidence: float

    # Order info
    direction: str = "long"
    status: OrderStatus = OrderStatus.PENDING

    # Execution (filled when position closes)
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    return_pct: Optional[float] = None
    pnl: Optional[float] = None

    # Timestamps
    created_at: str
    entered_at: Optional[str] = None
    exited_at: Optional[str] = None

    # Metadata
    run_id: str
    model: str
    prompt_version: str


class OrderBook:
    """
    Manages paper trading orders.

    Responsibilities:
    1. Track pending orders (waiting for T+1 entry)
    2. Track open positions
    3. Schedule exits (T+30)
    4. Record execution
    """

    def __init__(self, base_dir: str = "papertrading"):
        """
        Initialize order book.

        Args:
            base_dir: Directory for order book files
        """
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

        self._orders: Dict[str, PaperOrder] = {}
        self._load_orders()

    def _get_orders_file(self) -> Path:
        """Get orders file path."""
        return self.base_dir / "orders.json"

    def _load_orders(self) -> None:
        """Load orders from file."""
        orders_file = self._get_orders_file()
        if orders_file.exists():
            with open(orders_file, "r") as f:
                data = json.load(f)
                for order_data in data:
                    order = PaperOrder(**order_data)
                    self._orders[order.order_id] = order

    def _save_orders(self) -> None:
        """Save orders to file."""
        orders_file = self._get_orders_file()
        data = [order.model_dump(mode="json") for order in self._orders.values()]
        with open(orders_file, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def add_order(self, order: PaperOrder) -> None:
        """Add a new order."""
        self._orders[order.order_id] = order
        self._save_orders()

    def get_order(self, order_id: str) -> Optional[PaperOrder]:
        """Get an order by ID."""
        return self._orders.get(order_id)

    def get_pending_entries(self, as_of_date: date) -> List[PaperOrder]:
        """Get orders that should enter on a given date."""
        return [
            order
            for order in self._orders.values()
            if order.status == OrderStatus.PENDING and order.entry_date == as_of_date
        ]

    def get_pending_exits(self, as_of_date: date) -> List[PaperOrder]:
        """Get orders that should exit on a given date."""
        return [
            order
            for order in self._orders.values()
            if order.status == OrderStatus.OPEN and order.exit_date == as_of_date
        ]

    def get_open_positions(self) -> List[PaperOrder]:
        """Get all open positions."""
        return [
            order
            for order in self._orders.values()
            if order.status == OrderStatus.OPEN
        ]

    def mark_entered(
        self,
        order_id: str,
        entry_price: float,
    ) -> PaperOrder:
        """Mark an order as entered (position opened)."""
        order = self._orders[order_id]
        order.status = OrderStatus.OPEN
        order.entry_price = entry_price
        order.entered_at = datetime.utcnow().isoformat()
        self._save_orders()
        return order

    def mark_exited(
        self,
        order_id: str,
        exit_price: float,
    ) -> PaperOrder:
        """Mark an order as exited (position closed)."""
        order = self._orders[order_id]
        order.status = OrderStatus.CLOSED
        order.exit_price = exit_price
        order.exited_at = datetime.utcnow().isoformat()

        # Calculate return
        if order.entry_price:
            order.return_pct = (exit_price - order.entry_price) / order.entry_price

        self._save_orders()
        return order

    def cancel_order(self, order_id: str, reason: str) -> PaperOrder:
        """Cancel an order."""
        order = self._orders[order_id]
        order.status = OrderStatus.CANCELLED
        self._save_orders()
        return order

    def get_statistics(self) -> Dict[str, Any]:
        """Get order book statistics."""
        closed_orders = [
            o for o in self._orders.values() if o.status == OrderStatus.CLOSED
        ]

        if not closed_orders:
            return {
                "total_orders": len(self._orders),
                "pending": len([o for o in self._orders.values() if o.status == OrderStatus.PENDING]),
                "open": len([o for o in self._orders.values() if o.status == OrderStatus.OPEN]),
                "closed": 0,
                "cancelled": len([o for o in self._orders.values() if o.status == OrderStatus.CANCELLED]),
                "win_rate": None,
                "avg_return": None,
            }

        winning = [o for o in closed_orders if (o.return_pct or 0) > 0]
        returns = [o.return_pct for o in closed_orders if o.return_pct is not None]

        return {
            "total_orders": len(self._orders),
            "pending": len([o for o in self._orders.values() if o.status == OrderStatus.PENDING]),
            "open": len([o for o in self._orders.values() if o.status == OrderStatus.OPEN]),
            "closed": len(closed_orders),
            "cancelled": len([o for o in self._orders.values() if o.status == OrderStatus.CANCELLED]),
            "win_rate": len(winning) / len(closed_orders) if closed_orders else None,
            "avg_return": sum(returns) / len(returns) if returns else None,
        }

    def export_to_csv(self, filepath: Optional[Path] = None) -> Path:
        """Export orders to CSV."""
        if filepath is None:
            filepath = self.base_dir / "orders_export.csv"

        orders = list(self._orders.values())
        if not orders:
            return filepath

        fieldnames = list(orders[0].model_dump().keys())

        with open(filepath, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for order in orders:
                writer.writerow(order.model_dump(mode="json"))

        return filepath

    def open_position(
        self,
        symbol: str,
        entry_date: date,
        exit_date: date,
        signal_id: str,
        score: float,
        run_id: str = "paper",
        model: str = "gpt-4o-mini",
        prompt_version: str = "v1.0.0",
    ) -> PaperOrder:
        """
        Open a new paper position.

        Args:
            symbol: Stock symbol
            entry_date: Entry date (T+1)
            exit_date: Exit date (T+30)
            signal_id: Signal identifier
            score: Analysis score

        Returns:
            Created PaperOrder
        """
        import uuid

        order_id = f"paper_{uuid.uuid4().hex[:8]}"

        order = PaperOrder(
            order_id=order_id,
            signal_id=signal_id,
            symbol=symbol,
            event_date=entry_date,  # Approximate
            entry_date=entry_date,
            exit_date=exit_date,
            score=score,
            confidence=score,
            status=OrderStatus.PENDING,
            created_at=datetime.utcnow().isoformat(),
            run_id=run_id,
            model=model,
            prompt_version=prompt_version,
        )

        self.add_order(order)
        return order

    def close_due_positions(self, as_of_date: date) -> List[PaperOrder]:
        """
        Close all positions due to exit on a given date.

        Args:
            as_of_date: Date to check for exits

        Returns:
            List of closed orders
        """
        due_orders = self.get_pending_exits(as_of_date)
        closed = []

        for order in due_orders:
            # In real paper trading, would get actual exit price
            # For now, mark as exited with placeholder
            order.status = OrderStatus.CLOSED
            order.exited_at = datetime.utcnow().isoformat()
            closed.append(order)

        if closed:
            self._save_orders()

        return closed


# Alias for backwards compatibility
PaperOrderBook = OrderBook


# Global order book instance
_order_book: Optional[OrderBook] = None


def get_order_book() -> OrderBook:
    """Get the global order book instance."""
    global _order_book
    if _order_book is None:
        _order_book = OrderBook()
    return _order_book
