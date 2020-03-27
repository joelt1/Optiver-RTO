import asyncio
from typing import List, Tuple
from itertools import count
from ready_trader_one import BaseAutoTrader, Instrument, Lifespan, Side
import numpy as np
from scipy.stats import linregress as lin_reg

TAKER_FEE = 0.0002  # Fee paid to take an order
MAKER_FEE = -0.0001  # Fee received to make an order
PROFIT_MARGIN = None
VOL_LIM = 200  # Can't have more than this in the sum of individual volumes for each existing order
ORDER_COUNT_LIM = 20  # Can't have more than this number of open orders at any given time interval
POSITION_LIM = 100  # Can't exceed this value when opening an order
SPREAD = 200  # Difference between bid and ask prices
NUM_POINTS = 10
GRADIENT_THRESH = 0.25
CRIT_VAL = 0.1  # Hypothesis test critical value
GAUSSIAN_SHIFT = 1/2
Z_SCORE_SIGMA = 1
R_SQUARED_THRESH = 0.7
BUY_SELL_DIFF_THRESH = 10


class AutoTrader(BaseAutoTrader):
    def __init__(self, loop: asyncio.AbstractEventLoop):
        """Initialise a new instance of the AutoTrader class."""
        super(AutoTrader, self).__init__(loop)
        self.position = 0
        self.order_ids = count(1)
        self.waiting_for_server = False
        self.future_data = []
        self.etf_data = []
        self.remaining_volume = 0
        self.ask_id = 0
        self.bid_id = 0
        self.etf_order_book = []
        self.can_amend_order = False
        self.ask_remaining_volume = 0
        self.bid_remaining_volume = 0

    def on_error_message(self, client_order_id: int, error_message: bytes) -> None:
        """Called when the exchange detects an error.

        If the error pertains to a particular order, then the client_order_id
        will identify that order, otherwise the client_order_id will be zero.
        """
        self.logger.warning("Error with order %d: %s", client_order_id, error_message.decode())
        self.on_order_status_message(client_order_id, 0, 0, 0)

    @staticmethod
    def ideal_trade_volume(data):
        last_variance = data[-1]
        z_score = (last_variance - np.mean(data))/np.sqrt(np.var(data))
        # General function used for volume is V = V_MAX*e**(-b*x**2)
        return int(VOL_LIM*np.exp(-(1/2)*(z_score + GAUSSIAN_SHIFT)**2))

    def on_order_book_update_message(self, instrument: int, sequence_number: int, ask_prices: List[int],
                                     ask_volumes: List[int], bid_prices: List[int], bid_volumes: List[int]) -> None:
        """Called periodically to report the status of an order book.

        The sequence number can be used to detect missed or out-of-order
        messages. The five best available ask (i.e. sell) and bid (i.e. buy)
        prices are reported along with the volume available at each of those
        price levels.
        """
        if instrument == Instrument.FUTURE:
            future_order_book = [list(zip(ask_prices, ask_volumes)), list(zip(bid_prices, bid_volumes))]
            all_prices = np.array(ask_prices + bid_prices)
            all_volumes = np.array(ask_volumes + bid_volumes)
            # Weighted average of both bid and ask prices and volumes
            fair_value = int(round(np.sum(np.multiply(all_prices, np.divide(all_volumes, np.sum(all_volumes))))/100) *
                             100)
            if len(self.future_data) < NUM_POINTS:
                self.future_data.append(fair_value)
            else:
                self.future_data = self.future_data[1:] + [fair_value]
                if self.position == 0 and self.waiting_for_server is False:
                    self.can_amend_order = True
                    if len(self.etf_data) == NUM_POINTS:
                        slope, intercept, r_value, p_value, std_err = lin_reg(range(1, 11), self.future_data)
                        r_squared = r_value**2
                        # Case - no trend in futures market --> market maker role
                        # p-value for a hypothesis test whose null hypothesis is that the slope is zero
                        if p_value >= CRIT_VAL:
                            total_volume = self.ideal_trade_volume(self.etf_data)
                            side_volume = total_volume//2
                            self.logger.warning(f"Total trade volume: {total_volume}")
                            self.ask_id = next(self.order_ids)
                            self.bid_id = next(self.order_ids)
                            # Subcases - low volatility, confident market vs. high volatility, uncertain market
                            ask_price = (fair_value + SPREAD//2 if r_squared > R_SQUARED_THRESH else
                                         fair_value + SPREAD)
                            self.send_insert_order(self.ask_id, Side.SELL, ask_price, side_volume,
                                                   Lifespan.GOOD_FOR_DAY)
                            bid_price = (fair_value - SPREAD//2 if r_squared > R_SQUARED_THRESH else
                                         fair_value - SPREAD)
                            self.send_insert_order(self.bid_id, Side.BUY, bid_price, side_volume,
                                                   Lifespan.GOOD_FOR_DAY)
                            self.waiting_for_server = True
                        # Case - upward trending futures market/arbitrage opportunities --> market taker role
                elif np.abs(self.position) > BUY_SELL_DIFF_THRESH and self.waiting_for_server is False and \
                        self.can_amend_order is True:
                    self.logger.warning(f"Warning - cornering market with ETF position: {self.position}")
                    # Too many buy orders, need to readjust ask price
                    if self.position > 0:
                        self.send_cancel_order(self.ask_id)
                        self.ask_id = next(self.order_ids)
                        ask_price = self.etf_order_book[0][1][0]
                        self.send_insert_order(self.ask_id, Side.SELL, ask_price, self.ask_remaining_volume,
                                               Lifespan.GOOD_FOR_DAY)
                    # Too many sell orders, need to readjust bid price
                    else:
                        self.send_cancel_order(self.bid_id)
                        self.bid_id = next(self.order_ids)
                        bid_price = self.etf_order_book[1][1][0]
                        self.send_insert_order(self.bid_id, Side.BUY, bid_price, self.bid_remaining_volume,
                                               Lifespan.GOOD_FOR_DAY)
                    self.waiting_for_server = True
                    self.can_amend_order = False
        else:
            self.etf_order_book = [list(zip(ask_prices, ask_volumes)), list(zip(bid_prices, bid_volumes))]
            if len(self.etf_data) < NUM_POINTS:
                self.etf_data.append(np.var(ask_prices + bid_prices))
            else:
                self.etf_data = self.etf_data[1:] + [np.var(ask_prices + bid_prices)]

    def on_order_status_message(self, client_order_id: int, fill_volume: int, remaining_volume: int, fees: int) -> None:
        """Called when the status of one of your orders changes.

        The fill_volume is the number of lots already traded, remaining_volume
        is the number of lots yet to be traded and fees is the total fees for
        this order. Remember that you pay fees for being a market taker, but
        you receive fees for being a market maker, so fees can be negative.

        If an order is cancelled its remaining volume will be zero.
        """
        if client_order_id == self.ask_id:
            self.ask_remaining_volume = remaining_volume
        elif client_order_id == self.bid_id:
            self.bid_remaining_volume = remaining_volume
        self.waiting_for_server = False

    def on_position_change_message(self, future_position: int, etf_position: int) -> None:
        """Called when your position changes.

        Since every trade in the ETF is automatically hedged in the future,
        future_position and etf_position will always be the inverse of each
        other (i.e. future_position == -1 * etf_position).
        """
        self.position = etf_position
        self.logger.warning(f"Current ETF Position: {self.position}")
        self.waiting_for_server = False

    def on_trade_ticks_message(self, instrument: int, trade_ticks: List[Tuple[int, int]]) -> None:
        """Called periodically to report trading activity on the market.

        Each trade tick is a pair containing a price and the number of lots
        traded at that price since the last trade ticks message.
        """
        pass