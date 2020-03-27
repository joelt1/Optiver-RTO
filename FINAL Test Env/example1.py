import asyncio
import itertools

from typing import List

from ready_trader_one import BaseAutoTrader, Instrument, Lifespan, Side


class AutoTrader(BaseAutoTrader):
    def __init__(self, loop: asyncio.AbstractEventLoop):
        """Initialise a new instance of the AutoTrader class."""
        super(AutoTrader, self).__init__(loop)
        self.order_ids = itertools.count(1)
        self.ask_id = self.ask_price = self.bid_id = self.bid_price = 0

    def on_error_message(self, client_order_id: int, error_message: bytes) -> None:
        """Called when the exchange detects an error."""
        self.logger.warning("error with order %d: %s", client_order_id, error_message.decode())
        self.on_order_status_message(client_order_id, 0, 0, 0)

    def on_order_book_update_message(self, instrument: int, sequence_number: int, ask_prices: List[int],
                                     ask_volumes: List[int], bid_prices: List[int], bid_volumes: List[int]) -> None:
        """Called periodically to report the status of an order book."""
        if instrument == Instrument.FUTURE:
            best_bid = bid_prices[0]
            best_ask = ask_prices[0]

            if self.bid_id != 0 and best_bid != self.bid_price and best_bid != 0:
                self.send_cancel_order(self.bid_id)
                self.bid_id = 0
            if self.ask_id != 0 and best_ask != self.ask_price and best_ask != 0:
                self.send_cancel_order(self.ask_id)
                self.ask_id = 0

            if self.bid_id == 0 and best_bid != 0:
                self.bid_id = next(self.order_ids)
                self.bid_price = best_bid
                self.send_insert_order(self.bid_id, Side.BUY, best_bid, 1, Lifespan.GOOD_FOR_DAY)

            if self.ask_id == 0 and best_ask != 0:
                self.ask_id = next(self.order_ids)
                self.ask_price = best_ask
                self.send_insert_order(self.ask_id, Side.SELL, best_ask, 1, Lifespan.GOOD_FOR_DAY)

    def on_order_status_message(self, client_order_id: int, fill_volume: int, remaining_volume: int, fees: int) -> None:
        """Called when the status of one of your orders changes."""
        if remaining_volume == 0:
            if client_order_id == self.bid_id:
                self.bid_id = 0
            elif client_order_id == self.ask_id:
                self.ask_id = 0
