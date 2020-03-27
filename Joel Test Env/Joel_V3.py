import asyncio
from typing import List, Tuple
from itertools import count
from ready_trader_one import BaseAutoTrader, Instrument, Lifespan, Side
import numpy as np
from scipy.stats import linregress as lin_reg

ACTIVE_VOL_LIM = 200
ACTIVE_ORDER_COUNT_LIM = 2
V_MAX = 10
NET_POS_THRESHOLD = 60
STALE_THRESHOLD = 20
TICKS_PER_SEC = 4
NUM_POINTS = TICKS_PER_SEC*5
CRIT_VAL = 0.05


class AutoTrader(BaseAutoTrader):
    def __init__(self, loop: asyncio.AbstractEventLoop):
        """Initialise a new instance of the AutoTrader class."""
        super(AutoTrader, self).__init__(loop)
        self.future_data = []
        self.order_ids = count(1)
        self.net_position = 0

        self.best_future_ask_price = 0
        self.best_etf_ask_price = 0
        self.best_future_bid_price = 0
        self.best_etf_bid_price = 0
        self.fair_value_future = 0
        self.fair_value_etf = 0

        self.active_ask_orders = {}
        self.active_bid_orders = {}

    def on_error_message(self, client_order_id: int, error_message: bytes) -> None:
        """Called when the exchange detects an error.

        If the error pertains to a particular order, then the client_order_id
        will identify that order, otherwise the client_order_id will be zero.
        """
        self.logger.warning("Error with order %d: %s", client_order_id, error_message.decode())
        self.on_order_status_message(client_order_id, 0, 0, 0)

    def on_order_book_update_message(self, instrument: int, sequence_number: int, ask_prices: List[int],
                                     ask_volumes: List[int], bid_prices: List[int], bid_volumes: List[int]) -> None:
        """Called periodically to report the status of an order book.

        The sequence number can be used to detect missed or out-of-order
        messages. The five best available ask (i.e. sell) and bid (i.e. buy)
        prices are reported along with the volume available at each of those
        price levels.
        """
        # print(f"Pre execution ask orders: {self.active_ask_orders}")
        # print(f"Pre execution bid orders: {self.active_bid_orders}")
        if instrument == Instrument.FUTURE:
            self.fair_value_future = (ask_prices[0] + bid_prices[0])/2
            self.best_future_ask_price = ask_prices[0]
            self.best_future_bid_price = bid_prices[0]
            if len(self.future_data) < NUM_POINTS:
                self.future_data.append(self.fair_value_future)
            else:
                self.future_data = self.future_data[1:] + [self.fair_value_future]
        else:
            self.fair_value_etf = (ask_prices[0] + bid_prices[0])/2
            self.best_etf_ask_price = ask_prices[0]
            self.best_etf_bid_price = bid_prices[0]

        volume = V_MAX
        # print(f"Volume: {volume}")
        if np.abs(volume + self.net_position) >= NET_POS_THRESHOLD:
            self.dump_position()

        if len(self.active_ask_orders) < ACTIVE_ORDER_COUNT_LIM//2 and len(self.active_bid_orders) < \
                ACTIVE_ORDER_COUNT_LIM//2 and len(self.future_data) == NUM_POINTS:
            slope, intercept, r_value, p_value, std_err = lin_reg(range(NUM_POINTS), self.future_data)
            # Case 1) - futures market not trending, p-value is for hypothesis test that slope is equal to 0
            if p_value >= CRIT_VAL:
                ask_id = next(self.order_ids)
                # print(f"Ask price: {self.best_etf_ask_price}")
                self.send_insert_order(ask_id, Side.SELL, self.best_etf_ask_price, volume, Lifespan.GOOD_FOR_DAY)
                self.active_ask_orders[ask_id] = [self.best_etf_ask_price, volume, 0]

                bid_id = next(self.order_ids)
                # print(f"Bid price: {self.best_etf_bid_price}")
                self.send_insert_order(bid_id, Side.BUY, self.best_etf_bid_price, volume, Lifespan.GOOD_FOR_DAY)
                self.active_bid_orders[bid_id] = [self.best_etf_bid_price, volume, 0]
            # Case 2) - trending futures market
            else:
                # Upward trending futures market
                if slope > 0:
                    # Fair value of future higher than fair value of etf
                    if self.fair_value_future > self.fair_value_etf:
                        ask_id = next(self.order_ids)
                        # print(f"Ask price: {self.best_future_ask_price}")
                        self.send_insert_order(ask_id, Side.SELL, self.best_future_ask_price, volume, Lifespan.
                                               GOOD_FOR_DAY)
                        self.active_ask_orders[ask_id] = [self.best_future_ask_price, volume, 0]

                        bid_id = next(self.order_ids)
                        bid_price = max(self.best_future_bid_price, self.best_etf_ask_price)
                        # print(f"Bid price: {bid_price}")
                        self.send_insert_order(bid_id, Side.BUY, bid_price, volume, Lifespan.GOOD_FOR_DAY)
                        self.active_bid_orders[bid_id] = [bid_price, volume, 0]
                    # Fair value of future lower than fair value of etf
                    else:
                        ask_id = next(self.order_ids)
                        # print(f"Ask price: {self.best_etf_ask_price}")
                        self.send_insert_order(ask_id, Side.SELL, self.best_etf_ask_price, volume,
                                               Lifespan.GOOD_FOR_DAY)
                        self.active_ask_orders[ask_id] = [self.best_etf_ask_price, volume, 0]

                        bid_id = next(self.order_ids)
                        bid_price = max(self.best_future_ask_price, self.best_etf_bid_price)
                        # print(f"Bid price: {bid_price}")
                        self.send_insert_order(bid_id, Side.BUY, bid_price, volume, Lifespan.GOOD_FOR_DAY)
                        self.active_bid_orders[bid_id] = [bid_price, volume, 0]
                # Downward trending futures market
                else:
                    # Fair value of future higher than fair value of etf
                    if self.fair_value_future > self.fair_value_etf:
                        ask_id = next(self.order_ids)
                        ask_price = min(self.best_future_bid_price, self.best_etf_ask_price)
                        # print(f"Ask price: {ask_price}")
                        self.send_insert_order(ask_id, Side.SELL, ask_price, volume,
                                               Lifespan.GOOD_FOR_DAY)
                        self.active_ask_orders[ask_id] = [ask_price, volume, 0]

                        bid_id = next(self.order_ids)
                        # print(f"Bid price: {self.best_etf_bid_price}")
                        self.send_insert_order(bid_id, Side.BUY, self.best_etf_bid_price, volume, Lifespan.GOOD_FOR_DAY)
                        self.active_bid_orders[bid_id] = [self.best_etf_bid_price, volume, 0]
                    else:
                        ask_id = next(self.order_ids)
                        ask_price = min(self.best_future_ask_price, self.best_etf_bid_price)
                        # print(f"Ask price: {ask_price}")
                        self.send_insert_order(ask_id, Side.SELL, ask_price, volume,
                                               Lifespan.GOOD_FOR_DAY)
                        self.active_ask_orders[ask_id] = [ask_price, volume, 0]

                        bid_id = next(self.order_ids)
                        # print(f"Bid price: {self.best_future_bid_price}")
                        self.send_insert_order(bid_id, Side.BUY, self.best_future_bid_price, volume,
                                               Lifespan.GOOD_FOR_DAY)
                        self.active_bid_orders[bid_id] = [self.best_future_bid_price, volume, 0]

        # Dealing with stale orders
        for ask_order_id in list(self.active_ask_orders):
            self.active_ask_orders[ask_order_id][2] += 1
            if self.active_ask_orders[ask_order_id][2] >= STALE_THRESHOLD:
                self.send_cancel_order(ask_order_id)
                self.active_ask_orders.pop(ask_order_id)

        for bid_order_id in list(self.active_bid_orders):
            self.active_bid_orders[bid_order_id][2] += 1
            if self.active_bid_orders[bid_order_id][2] >= STALE_THRESHOLD:
                self.send_cancel_order(bid_order_id)
                self.active_bid_orders.pop(bid_order_id)

        # print(f"Post execution ask orders: {self.active_ask_orders}")
        # print(f"Post execution bid orders: {self.active_bid_orders}")
        # print("\n")

    def dump_position(self):
        for ask_order_id in self.active_ask_orders:
            self.send_cancel_order(ask_order_id)

        for bid_order_id in self.active_bid_orders:
            self.send_cancel_order(bid_order_id)

        # Ask orders not going through
        if self.net_position > 0:
            ask_id = next(self.order_ids)
            self.send_insert_order(ask_id, Side.SELL, self.best_etf_ask_price, np.abs(self.net_position),
                                   Lifespan.GOOD_FOR_DAY)
            self.active_ask_orders[ask_id] = [self.best_etf_ask_price, np.abs(self.net_position), 0]
        # Bid orders not going through
        else:
            bid_id = next(self.order_ids)
            self.send_insert_order(bid_id, Side.BUY, self.best_etf_bid_price, np.abs(self.net_position),
                                   Lifespan.GOOD_FOR_DAY)
            self.active_bid_orders[bid_id] = [self.best_etf_bid_price, np.abs(self.net_position), 0]

    def on_order_status_message(self, client_order_id: int, fill_volume: int, remaining_volume: int, fees: int) -> None:
        """Called when the status of one of your orders changes.

        The fill_volume is the number of lots already traded, remaining_volume
        is the number of lots yet to be traded and fees is the total fees for
        this order. Remember that you pay fees for being a market taker, but
        you receive fees for being a market maker, so fees can be negative.

        If an order is cancelled its remaining volume will be zero.
        """
        if client_order_id in self.active_ask_orders.keys():
            if remaining_volume == 0:
                self.active_ask_orders.pop(client_order_id, None)
            else:
                try:
                    self.active_ask_orders[client_order_id][1] = remaining_volume
                except KeyError:
                    pass
        else:
            if remaining_volume == 0:
                self.active_bid_orders.pop(client_order_id, None)
            else:
                try:
                    self.active_bid_orders[client_order_id][1] = remaining_volume
                except KeyError:
                    pass

    def on_position_change_message(self, future_position: int, etf_position: int) -> None:
        """Called when your position changes.

        Since every trade in the ETF is automatically hedged in the future,
        future_position and etf_position will always be the inverse of each
        other (i.e. future_position == -1 * etf_position).
        """
        self.net_position = etf_position
        # print(f"\nNet position: {self.net_position}\n")

    def on_trade_ticks_message(self, instrument: int, trade_ticks: List[Tuple[int, int]]) -> None:
        """Called periodically to report trading activity on the market.

        Each trade tick is a pair containing a price and the number of lots
        traded at that price since the last trade ticks message.
        """
        pass
