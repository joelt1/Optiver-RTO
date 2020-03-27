import asyncio
from typing import List, Tuple
from itertools import count
from ready_trader_one import BaseAutoTrader, Instrument, Lifespan, Side
import numpy as np
from scipy.stats import linregress as lin_reg

V_MAX = 20  # Maximum individual trade volume
POSITION_LIM = 100  # Can't exceed this value when opening an order
UPPER_SPREAD = 100
LOWER_SPREAD = 100
NUM_POINTS = 10
CRIT_VAL = 0.05  # Hypothesis test critical value
GAUSSIAN_SHIFT = 1/2
Z_SCORE_SIGMA = 1
R_SQUARED_THRESH = 0.8
BUY_SELL_DIFF_THRESH = 10
MIN_TRADE_VOL = 5


class AutoTrader(BaseAutoTrader):
    def __init__(self, loop: asyncio.AbstractEventLoop):
        """Initialise a new instance of the AutoTrader class."""
        super(AutoTrader, self).__init__(loop)
        self.net_position = 0
        self.order_ids = count(1)
        self.waiting_for_server = False
        self.future_data = []
        self.etf_data = []
        self.etf_order_book = []
        self.active_orders = {}
        self.last_order_id = None

    def on_error_message(self, client_order_id: int, error_message: bytes) -> None:
        """Called when the exchange detects an error.

        If the error pertains to a particular order, then the client_order_id
        will identify that order, otherwise the client_order_id will be zero.
        """
        self.logger.warning("Error with order %d: %s", client_order_id, error_message.decode())
        for order_id in self.active_orders:
            self.send_cancel_order(order_id)
        self.active_orders = {}
        self.waiting_for_server = False
        self.on_order_status_message(client_order_id, 0, 0, 0)

    @staticmethod
    def ideal_trade_volume(data):
        last_variance = data[-1]
        if np.sqrt(np.var(data)) == 0:
            return V_MAX
        else:
            z_score = (last_variance - np.mean(data)) / np.sqrt(np.var(data))
            if z_score < GAUSSIAN_SHIFT:
                return V_MAX
            else:
                # General function used for volume is V = V_MAX*e**(-b*x**2)
                return max(int(round(V_MAX * np.exp(-(1 / 2) * (z_score + GAUSSIAN_SHIFT) ** 2))), MIN_TRADE_VOL)

    def on_order_book_update_message(self, instrument: int, sequence_number: int, ask_prices: List[int],
                                     ask_volumes: List[int], bid_prices: List[int], bid_volumes: List[int]) -> None:
        """Called periodically to report the status of an order book.

        The sequence number can be used to detect missed or out-of-order
        messages. The five best available ask (i.e. sell) and bid (i.e. buy)
        prices are reported along with the volume available at each of those
        price levels.
        """
        if instrument == Instrument.FUTURE:
            best_ask = ask_prices[0]
            best_bid = bid_prices[0]
            # Average of best ask and bid price rounded to nearest multiple of tick size
            fair_value = int(round(((best_ask + best_bid)/2)/100)*100)
            if len(self.future_data) < NUM_POINTS:
                self.future_data.append(fair_value)
            else:
                self.future_data = self.future_data[1:] + [fair_value]
        else:
            self.etf_order_book = [list(zip(ask_prices, ask_volumes)), list(zip(bid_prices, bid_volumes))]
            if len(self.etf_data) < NUM_POINTS:
                self.etf_data.append(np.var(ask_prices + bid_prices))
            else:
                self.etf_data = self.etf_data[1:] + [np.var(ask_prices + bid_prices)]
        # Primary function for inserting new pairs of orders (bid and ask)
        if len(self.future_data) == NUM_POINTS and len(self.etf_data) == NUM_POINTS:
            # Most recent stored fair value of future
            fair_value = self.future_data[-1]
            if self.waiting_for_server is False and len(self.active_orders) == 0:
                slope, intercept, r_value, p_value, std_err = lin_reg(range(NUM_POINTS), self.future_data)
                r_squared = r_value**2
                # Case 1) - no trend in futures market --> market maker role
                # p-value for a hypothesis test whose null hypothesis is that the slope is zero
                # if p_value >= CRIT_VAL:
                volume = self.ideal_trade_volume(self.etf_data)
                ask_id = next(self.order_ids)
                bid_id = next(self.order_ids)
                # Subcase 1) - low volatility, confident market
                self.logger.warning(f"R squared: {r_squared}")
                if r_squared > R_SQUARED_THRESH:
                    ask_price = int(fair_value + UPPER_SPREAD)
                    bid_price = int(fair_value - LOWER_SPREAD)
                # Subcase 2) - high volatility, uncertain market
                else:
                    # Second best ask and bid price in etf order book
                    ask_price = self.etf_order_book[0][1][0]
                    bid_price = self.etf_order_book[1][1][0]
                self.logger.warning("Executing main function for inserting new orders")
                self.send_insert_order(ask_id, Side.SELL, ask_price, volume, Lifespan.GOOD_FOR_DAY)
                self.send_insert_order(bid_id, Side.BUY, bid_price, volume, Lifespan.GOOD_FOR_DAY)
                # Store ask volume as negative, bid volume as positive
                self.active_orders[ask_id] = [-volume]
                self.active_orders[bid_id] = [volume]
                self.waiting_for_server = True
                # Case 2) - upward trending futures market/arbitrage opportunities --> market taker role
        for order_id in self.active_orders:
            self.logger.warning("Appending previous value for each order in self.active_orders")
            self.active_orders[order_id].append(self.active_orders[order_id][-1])
            # Ensure list will always only store 2 volumes at any given time
            if len(self.active_orders[order_id]) == 5:
                self.active_orders[order_id] = self.active_orders[order_id][1:]
        if self.net_position > 0 and self.waiting_for_server is True:
            for order_id in list(self.active_orders):
                # Ensuring we obtain the relevant ask order
                if self.active_orders[order_id][-1] < 0 and len(self.active_orders[order_id]) == 4 and \
                        self.active_orders[order_id][-1] == self.active_orders[order_id][-4]:
                    self.logger.warning("Executing if self.net_position > 0 and self.waiting_for_server is True:")
                    self.send_cancel_order(order_id)
                    self.active_orders.pop(order_id)
                    ask_id = next(self.order_ids)
                    # Best bid  price in etf order book
                    ask_price = self.etf_order_book[0][0][0]  # Might change this to cross the spread if doesn't w
                    volume = int(np.abs(self.net_position))
                    self.send_insert_order(ask_id, Side.SELL, ask_price, volume, Lifespan.GOOD_FOR_DAY)
                    self.active_orders[ask_id] = [-volume]
        elif self.net_position < 0 and self.waiting_for_server is True:
            for order_id in list(self.active_orders):
                # Ensuring we obtain the relevant bid order
                if self.active_orders[order_id][-1] > 0 and len(self.active_orders[order_id]) == 4 and \
                        self.active_orders[order_id][-1] == self.active_orders[order_id][-4]:
                    self.logger.warning("Executing elif self.net_position < 0 and self.waiting_for_server is True:")
                    self.send_cancel_order(order_id)
                    self.active_orders.pop(order_id)
                    bid_id = next(self.order_ids)
                    # Best ask price in etf order book
                    bid_price = self.etf_order_book[1][0][0]  # Might change this to cross the spread if doesn't w
                    volume = int(np.abs(self.net_position))
                    self.send_insert_order(bid_id, Side.BUY, bid_price, volume, Lifespan.GOOD_FOR_DAY)
                    self.active_orders[bid_id] = [volume]
        else:
            for order_id in list(self.active_orders):
                if np.abs(self.active_orders[order_id][-1]) > 0 and len(self.active_orders[order_id]) == 4 and \
                        self.active_orders[order_id][-1] == self.active_orders[order_id][-4]:
                    self.logger.warning("Executing else:")
                    self.send_cancel_order(order_id)
                    self.active_orders.pop(order_id)
        # Can open new set of orders once net ETF position is 0
        volume = int(np.abs(self.net_position))
        if np.abs(self.net_position) <= BUY_SELL_DIFF_THRESH and self.waiting_for_server is True:
            order_volume_zero = True
            # Secondary check to ensure volume on both sides has been filled
            for order_id in self.active_orders:
                if self.active_orders[order_id][-1] != 0:
                    self.logger.warning("Trying to reset order book but one order in active orders dict is non-zero")
                    self.logger.warning(f"Active orders: {self.active_orders}")
                    order_volume_zero = False
                    break
            if order_volume_zero:
                self.logger.warning("Resetting order book and flag in order to execute main function for inserting"
                                    "orders again")
                self.active_orders = {}
                self.waiting_for_server = False
        # Cornering market case
        elif np.abs(self.net_position) > BUY_SELL_DIFF_THRESH and self.waiting_for_server is True:
            can_cancel = True
            self.logger.warning("Trying to fix position because cornering market")
            self.logger.warning(f"Active orders: {self.active_orders}")
            for order_id in self.active_orders:
                if len(self.active_orders[order_id]) != 4:
                    can_cancel = False
                elif len(self.active_orders[order_id]) == 4 and len(set(self.active_orders[order_id])) > 1:
                    can_cancel = False
            if can_cancel:
                self.logger.warning("Cancelling all orders")
                for order_id in self.active_orders:
                    self.send_cancel_order(order_id)
                if self.net_position > 0:
                    self.logger.warning(f"Net position {self.net_position}, inserting ask order")
                    ask_id = next(self.order_ids)
                    # Best ask price in etf order book
                    ask_price = self.etf_order_book[1][0][0]
                    self.send_insert_order(ask_id, Side.SELL, ask_price, volume, Lifespan.FILL_AND_KILL)
                    self.active_orders[ask_id] = [-volume]
                elif self.net_position < 0:
                    self.logger.warning(f"Net position {self.net_position}, inserting bid order")
                    bid_id = next(self.order_ids)
                    # Best bid price in etf order book
                    bid_price = self.etf_order_book[0][0][0]
                    self.send_insert_order(bid_id, Side.BUY, bid_price, volume, Lifespan.FILL_AND_KILL)
                    self.active_orders[bid_id] = [volume]
        # Setting self.active_orders = {} and ensuring FAK gets removed somehow
        if len(self.active_orders) == 0:
            self.logger.warning("Manually resetting waiting for server flag")
            self.waiting_for_server = False
        self.logger.warning(f"Active orders: {self.active_orders}")

    def on_order_status_message(self, client_order_id: int, fill_volume: int, remaining_volume: int, fees: int) -> None:
        """Called when the status of one of your orders changes.

        The fill_volume is the number of lots already traded, remaining_volume
        is the number of lots yet to be traded and fees is the total fees for
        this order. Remember that you pay fees for being a market taker, but
        you receive fees for being a market maker, so fees can be negative.

        If an order is cancelled its remaining volume will be zero.
        """
        # Update remaining volumes for each order
        self.last_order_id = client_order_id
        self.logger.warning(f"Last order id: {self.last_order_id}")
        self.logger.warning(f"Last remaining volume: {remaining_volume}")
        try:
            self.active_orders[client_order_id].append(-remaining_volume if self.active_orders[client_order_id][-1] < 0
                                                       else remaining_volume)
            if len(self.active_orders[client_order_id]) == 5:
                self.active_orders[client_order_id] = self.active_orders[client_order_id][1:]
        # Will reach here if cancel order above, reset active orders dict and then try to update active orders from here
        except KeyError:
            pass

    def on_position_change_message(self, future_position: int, etf_position: int) -> None:
        """Called when your position changes.

        Since every trade in the ETF is automatically hedged in the future,
        future_position and etf_position will always be the inverse of each
        other (i.e. future_position == -1 * etf_position).
        """
        self.net_position = etf_position
        self.logger.warning(f"Current ETF Position: {self.net_position}")

    def on_trade_ticks_message(self, instrument: int, trade_ticks: List[Tuple[int, int]]) -> None:
        """Called periodically to report trading activity on the market.

        Each trade tick is a pair containing a price and the number of lots
        traded at that price since the last trade ticks message.
        """
        pass
