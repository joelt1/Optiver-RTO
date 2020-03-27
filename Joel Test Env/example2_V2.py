import asyncio
import itertools

from typing import List

from ready_trader_one import BaseAutoTrader, Instrument, Lifespan, Side


class AutoTrader(BaseAutoTrader):
    def __init__(self, loop: asyncio.AbstractEventLoop):
        """Initialise a new instance of the AutoTrader class."""
        super(AutoTrader, self).__init__(loop)
        self.order_ids = itertools.count(1)
        self.ask_ids = []
        self.prices = []
        self.bid_ids = []
        self.position = 0
        self.orders = {}
        self.time = 0
        self.fill_time = 0

        self.active_ask_orders = {}
        self.active_bid_orders = {}

    def on_error_message(self, client_order_id: int, error_message: bytes) -> None:
        """Called when the exchange detects an error."""
        self.logger.warning("error with order %d: %s", client_order_id, error_message.decode())
        self.on_order_status_message(client_order_id, 0, 0, 0)
        # print(error_message)

    def on_order_book_update_message(self, instrument: int, sequence_number: int, ask_prices: List[int],
                                     ask_volumes: List[int], bid_prices: List[int], bid_volumes: List[int]) -> None:
        self.time = sequence_number
        """Called periodically to report the status of an order book."""
        # print(f"Pre execution ask orders: {self.active_ask_orders}")
        # print(f"Pre execution bid orders: {self.active_bid_orders}")
        if instrument == Instrument.FUTURE and self.time > self.fill_time + 5:
            new_bid_price = bid_prices[0] - self.position * 100 if bid_prices[0] != 0 else 0
            new_ask_price = ask_prices[0] - self.position * 100 if ask_prices[0] != 0 else 0

            if len(self.bid_ids) >= 4:
                bid_id = self.bid_ids.pop(0)
                self.send_cancel_order(bid_id)
            if len(self.ask_ids) >= 4:
                ask_id = self.ask_ids.pop(0)
                self.send_cancel_order(ask_id)

            if len(self.bid_ids) < 4 and new_bid_price != 0 and self.position < 100 and new_bid_price not in self.prices:
                bid_id = next(self.order_ids)
                self.bid_ids.append(bid_id)
                self.prices.append(new_bid_price)
                self.orders[bid_id] = new_bid_price
                # print(f"Bid price: {new_bid_price}")
                self.send_insert_order(bid_id, Side.BUY, new_bid_price, 1, Lifespan.GOOD_FOR_DAY)
                self.active_bid_orders[bid_id] = [new_bid_price, 1]

            if len(self.ask_ids) < 4 and new_ask_price != 0 and self.position > -100  and new_ask_price not in self.prices:
                ask_id = next(self.order_ids)
                self.ask_ids.append(ask_id)
                self.prices.append(new_ask_price)
                self.orders[ask_id] = new_ask_price
                # print(f"Ask price: {new_ask_price}")
                self.send_insert_order(ask_id, Side.SELL, new_ask_price, 1, Lifespan.GOOD_FOR_DAY)
                self.active_ask_orders[ask_id] = [new_ask_price, 1]
        # print(f"Post execution ask orders: {self.active_ask_orders}")
        # print(f"Post execution bid orders: {self.active_bid_orders}")
        # print("\n")

    def on_order_status_message(self, client_order_id: int, fill_volume: int, remaining_volume: int, fees: int) -> None:
        """Called when the status of one of your orders changes."""
        # print(f"\nOrder id: {client_order_id}, Remaining volume: {remaining_volume}\n")
        if remaining_volume == 0:
            price = self.orders.pop(client_order_id)
            self.prices.remove(price)
            self.fill_time = self.time
            if client_order_id in self.bid_ids:
                self.bid_ids.remove(client_order_id)
            elif client_order_id in self.ask_ids:
                self.ask_ids.remove(client_order_id)

            if client_order_id in self.active_bid_orders:
                self.active_bid_orders.pop(client_order_id)
            elif client_order_id in self.active_ask_orders:
                self.active_ask_orders.pop(client_order_id)

    def on_position_change_message(self, future_position: int, etf_position: int) -> None:
        """Called when your position changes."""
        self.position = etf_position
