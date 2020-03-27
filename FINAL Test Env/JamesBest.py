import asyncio
import numpy as np
import itertools
import time

from typing import List, Tuple

from ready_trader_one import BaseAutoTrader, Instrument, Lifespan, Side

MIN_SPREAD = 50 # This is the spread for each side of fair value (TESTVAL = 50)
PRESSURE_SPREAD = 50 # Degree to which pressure is added. (TESTVAL = 50)
MAX_SIDE_ORDERS = 4 # Dont let this go higher than 4 else  no room for cancels (TESTVAL = 4)
SET_VOLUME = 10 #(TESTVAL = 2) If we can increase the volume without increasing volitility, then we can increase our score
BIG_VOL = 20 # For stable markets (TESTVAL = 3)
BIG_PRESSURE = 4 # Pressure value for BIG_VOL to occur (TESTVAL = -2)
MIN_PRESSURE = 0 # (TESTVAL = -2) Negative value allows us to take advantage of large spreads in the market when safe
MAX_PRESSURE = 10 # Just incase things break and the pressure goes too far up
RETURN_STRENGTH = 100 # When etf_position != 0, we push it back towards 0 with this value. Be careful of it being to strong
DUMP_POSITION = 100
# NTIERS relative to the volume indicates how much can be sold at a particular time
DROP_PER_TIER = 1
TIER_SIZE = 15
MAX_FREQUENCY = 10

savefile = open("logs.txt", "w") # Personal Logs with information about the bot as it operates
savefile.close()

print("Ready Trader One")
class AutoTrader(BaseAutoTrader):
    def __init__(self, loop: asyncio.AbstractEventLoop):
        """Initialise a new instance of the AutoTrader class."""
        super(AutoTrader, self).__init__(loop)
        # Define basic variables
        self.bid_orders = np.array([])
        self.ask_orders = np.array([])
        self.order_ids = itertools.count(1)
        
        self.bid_pressure = 0
        self.ask_pressure = 0

        self.etf_position = 0
        self.count = 0

        self.time = time.time()
        self.requests = 0

    def log(self, line):
        """ Log Activities in seperate log file """
        try:
            print(line)
            savefile = open("logs.txt", "a+")
            savefile.write(str(line) + '\n')
            savefile.close()
        except:
            self.log("Error in message")

    def check_volume(self):
        return self.side_volume(self.bid_orders) + self.side_volume(self.ask_orders)

    def side_volume(self, arr):
        if len(arr) > 0:
            return np.sum(arr[:, 2])
        else:
            return 0


    def on_error_message(self, client_order_id: int, error_message: bytes) -> None:
        """Called when the exchange detects an error.

        If the error pertains to a particular order, then the client_order_id
        will identify that order, otherwise the client_order_id will be zero.
        """
        """ Optivers Code throws back cross order error messages, even though there are
            none. The orders till go through though so Im silencing the error on our logs.
            It will still appear in optivers logs through. """
        
        self.logger.warning("error with order %d: %s", client_order_id, error_message.decode())
        self.on_order_status_message(client_order_id, 0, 0, 0)
        self.log(error_message)
                

    def on_order_book_update_message(self, instrument: int, sequence_number: int, ask_prices: List[int],
                                     ask_volumes: List[int], bid_prices: List[int], bid_volumes: List[int]) -> None:
        """Called periodically to report the status of an order book.

        The sequence number can be used to detect missed or out-of-order
        messages. The five best available ask (i.e. sell) and bid (i.e. buy)
        prices are reported along with the volume available at each of those
        price levels.
        """

        """ The bid and ask pressure shift the bid and ask prices towards values where they will be
            accepted by the market. When a transaction does occur, the pressure decreases and prices
            become less competitive. When no transaction occurs, Pressure increases.
            There is some pressure adjustment due to the value of the etf position, but the main
            influence of the etf position is considered seperately due to the Pressure being very slow
            to respond to changes in position.

            The main idea I found is that the most successful auto-traders aim to keep the etf-position
            around zero by pricing their bids and asks correctly rather than using logic statements. By
            adding pressure onto the prices, the prices will only be as competitive as they need to be."""

        if instrument == Instrument.FUTURE:
            def intval(num):
                return int(round((num)/100)*100)

            # I dont want any trades to occur if etf_position gets too high. While the bot freezes here, we wont be booted from the match and will still be scored.
            flag = 'flag 3'
            if bid_prices[0] != 0 and ask_prices[0] != 0 and abs(self.etf_position) < DUMP_POSITION:

                """ Implement Tiered Volume """
                volume = BIG_VOL - (abs(self.etf_position)//TIER_SIZE)*DROP_PER_TIER
                
                if volume < SET_VOLUME or self.bid_pressure > BIG_PRESSURE or self.ask_pressure > BIG_PRESSURE:
                    volume = min(SET_VOLUME, volume)

                fair_value = np.mean(bid_prices + ask_prices) # Approximate Fair Value
                spread = max((ask_prices[0] - bid_prices[0])/2 - 50, MIN_SPREAD) # Approximate spread
                shift = self.bid_pressure - self.ask_pressure
                """ The shift scheme is so that bid price always remains below ask price """
                bid_price = intval(fair_value - spread + PRESSURE_SPREAD*shift - RETURN_STRENGTH*self.etf_position/volume)
                ask_price = intval(fair_value + spread + PRESSURE_SPREAD*shift - RETURN_STRENGTH*self.etf_position/volume)
                
                if self.count % 10 == 0:
                    # Record stuff relevant to monitaring the performance of the bot
                    string = "{}, requests {} , Spread {}, Bid Pressure {}, Ask Pressure {}, Position {}".format(self.count, self.requests, ask_price - bid_price, self.bid_pressure, self.ask_pressure, self.etf_position)
                    self.log(string)
                
                self.count += 1
                
                if len(self.bid_orders) < MAX_SIDE_ORDERS and self.etf_position < DUMP_POSITION - self.side_volume(self.bid_orders) - volume:
                    can_trade = True
                    if len(self.ask_orders) > 0:
                        if np.any(bid_price >= self.ask_orders[:, 1]):
                            can_trade = False
                            """ Cross Order with Bid Prices going up ... Up Trend """
                            orders_available = 10 - len(self.bid_orders) - len(self.ask_orders)
                            wash_trades = self.ask_orders[bid_price >= self.ask_orders[:, 1]]
                            for i in range(np.min([orders_available, len(wash_trades)])):
                                if self.requests < MAX_FREQUENCY:
                                    ask_id = self.ask_orders[0, 0]
                                    self.send_cancel_order(ask_id)
                                    self.ask_orders = np.delete(self.ask_orders, 0, 0)
                                    self.requests += 1

                    if self.check_volume() > 200 - 2*volume:
                        can_trade = False
                            
                            
                    if can_trade and self.requests < MAX_FREQUENCY:
                        bid_id = next(self.order_ids)
                        self.send_insert_order(bid_id, Side.BUY, bid_price, volume, Lifespan.GOOD_FOR_DAY)
                        if len(self.bid_orders) > 0:
                            self.bid_orders = np.append(self.bid_orders, [[bid_id, bid_price, volume]], 0)
                        else:
                            self.bid_orders = np.array([[bid_id, bid_price, volume]])
                        self.requests += 1

                else:
                    if len(self.bid_orders) > 0 and self.requests < MAX_FREQUENCY:
                        bid_id = self.bid_orders[0, 0]
                        self.send_cancel_order(bid_id)
                        self.requests += 1
                        self.bid_orders = np.delete(self.bid_orders, 0, 0)
                        if self.bid_pressure < MAX_PRESSURE:
                            self.bid_pressure += 1


                if len(self.ask_orders) < MAX_SIDE_ORDERS and self.etf_position > -DUMP_POSITION + self.side_volume(self.ask_orders) + volume:
                    can_trade = True
                    if len(self.bid_orders) > 0:
                        if np.any(ask_price <= self.bid_orders[:, 1]):
                            """ Ask Prices Are going Down Implying a down trend"""
                            can_trade = False
                            orders_available = 10 - len(self.bid_orders) - len(self.ask_orders)
                            wash_trades = self.bid_orders[ask_price <= self.bid_orders[:, 1]]
                            for i in range(np.min([orders_available, len(wash_trades)])):
                                if self.requests < MAX_FREQUENCY:
                                    bid_id = self.bid_orders[0, 0]
                                    self.send_cancel_order(bid_id)
                                    self.requests += 1
                                    self.bid_orders = np.delete(self.bid_orders, 0, 0)

                    if self.check_volume() > 200 - 2*volume:
                        can_trade = False
                          
                    if can_trade and self.requests < MAX_FREQUENCY:
                        ask_id = next(self.order_ids)
                        self.send_insert_order(ask_id, Side.SELL, ask_price, volume, Lifespan.GOOD_FOR_DAY)
                        if len(self.ask_orders) > 0:
                            self.ask_orders = np.append(self.ask_orders, [[ask_id, ask_price, volume]], 0)
                        else:
                            self.ask_orders = np.array([[ask_id, ask_price, volume]]) 
                        self.requests += 1
                        
                else:
                    if len(self.ask_orders) > 0 and self.requests < MAX_FREQUENCY:
                        ask_id = self.ask_orders[0, 0]
                        self.send_cancel_order(ask_id)
                        self.ask_orders = np.delete(self.ask_orders, 0, 0)
                        self.requests += 1
                        if self.ask_pressure < MAX_PRESSURE:
                            self.ask_pressure += 1

            if time.time() - self.time > 1:
                self.time = time.time()
                self.requests = 0      

        
    def on_order_status_message(self, client_order_id: int, fill_volume: int, remaining_volume: int, fees: int) -> None:
        """Called when the status of one of your orders changes.

        The fill_volume is the number of lots already traded, remaining_volume
        is the number of lots yet to be traded and fees is the total fees for
        this order. Remember that you pay fees for being a market taker, but
        you receive fees for being a market maker, so fees can be negative.

        If an order is cancelled its remaining volume will be zero.
        """
        
        if remaining_volume == 0:
            # Decrease Pressure on successful trades
            if len(self.bid_orders) > 0:
                if client_order_id in self.bid_orders[:, 0]:
                    self.bid_orders = np.delete(self.bid_orders, np.where(self.bid_orders[:, 0] == client_order_id), 0)
                    if self.bid_pressure > MIN_PRESSURE:
                        self.bid_pressure -= 1
            if len(self.ask_orders) > 0:
                if client_order_id in self.ask_orders[:, 0]:
                    self.ask_orders = np.delete(self.ask_orders, np.where(self.ask_orders[:, 0] == client_order_id), 0)
                    if self.ask_pressure > MIN_PRESSURE:
                        self.ask_pressure -= 1
        else:
            if len(self.bid_orders) > 0:
                if client_order_id in self.bid_orders[:, 0]:
                    index = np.where(self.bid_orders[:, 0] == client_order_id)
                    self.bid_orders[index, 2] = remaining_volume
                    
            if len(self.ask_orders) > 0:
                if client_order_id in self.ask_orders[:, 0]:
                    index = np.where(self.ask_orders[:, 0] == client_order_id)
                    self.ask_orders[index, 2] = remaining_volume


    def on_position_change_message(self, future_position: int, etf_position: int) -> None:
        """Called when your position changes.

        Since every trade in the ETF is automatically hedged in the future,
        future_position and etf_position will always be the inverse of each
        other (i.e. future_position == -1 * etf_position).
        """
        self.etf_position = etf_position # Update etf position

        
    def on_trade_ticks_message(self, instrument: int, trade_ticks: List[Tuple[int, int]]) -> None:
        """Called periodically to report trading activity on the market.

        Each trade tick is a pair containing a price and the number of lots
        traded at that price since the last trade ticks message.
        """
        pass
