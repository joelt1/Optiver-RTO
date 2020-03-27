import asyncio
import numpy as np
import itertools

from typing import List, Tuple

from ready_trader_one import BaseAutoTrader, Instrument, Lifespan, Side

MIN_SPREAD = 50 # This is the spread for each side of fair value
PRESSURE_SPREAD = 50 # Degree to which pressure is added. Must be multiple of 100
MAX_SIDE_ORDERS = 4 # Dont let this go higher than 4 else  no room for cancels
SET_VOLUME = 1
BIG_VOL = 2
MIN_PRESSURE = -1 # Negative value allows us to take advantage of large spreads in the market when safe
MAX_PRESSURE = 100
THRESHHOLD_POSITION = 5
HIGHEST_POSITION = 10
RETURN_STRENGTH = 2
DUMP_POSITION = 50


savefile = open("logs.txt", "w")
savefile.close()

print("Ready Trader One")
class AutoTrader(BaseAutoTrader):
    def __init__(self, loop: asyncio.AbstractEventLoop):
        """Initialise a new instance of the AutoTrader class."""
        super(AutoTrader, self).__init__(loop)
        self.bid_ids = []
        self.ask_ids = []
        self.order_ids = itertools.count(1)
        self.active_orders = {}
        
        self.bid_volume = SET_VOLUME
        self.ask_volume = SET_VOLUME
        self.bid_pressure = 0
        self.ask_pressure = 0
        
        self.etf_position = 0
        self.count = 0

        self.previous_sequence = 0
        self.best_prices = [0, 0]

    def log(self, line):
        """ Log Activities in seperate log file """
        try:
            print(line)
            savefile = open("logs.txt", "a+")
            savefile.write(str(line) + '\n')
            savefile.close()
        except:
            self.log("Error in message")
        
    def on_error_message(self, client_order_id: int, error_message: bytes) -> None:
        """Called when the exchange detects an error.

        If the error pertains to a particular order, then the client_order_id
        will identify that order, otherwise the client_order_id will be zero.
        """
        """ Optivers Code throws back cross order error messages, even though there are
            none. The orders till go through though so Im just silencing the code. """

        try:
            if "cross" in str(error_message):
                pass
            else:
                self.log("error with order {}: {}".format(client_order_id,error_message.decode()))
                self.logger.warning("error with order %d: %s", client_order_id, error_message.decode())
                self.on_order_status_message(client_order_id, 0, 0, 0)
        except:
            print("ERROR of ERRORS")

    def on_order_book_update_message(self, instrument: int, sequence_number: int, ask_prices: List[int],
                                     ask_volumes: List[int], bid_prices: List[int], bid_volumes: List[int]) -> None:
        """Called periodically to report the status of an order book.

        The sequence number can be used to detect missed or out-of-order
        messages. The five best available ask (i.e. sell) and bid (i.e. buy)
        prices are reported along with the volume available at each of those
        price levels.
        """
        flag = ''
        try:
            if instrument == Instrument.FUTURE:
                flag = "flag 0"
                def intval(num):
                    return int(round((num)/100)*100)
                
                if bid_prices[0] != 0 and ask_prices[0] != 0 and sequence_number > self.previous_sequence and abs(self.etf_position) < DUMP_POSITION:
                    self.best_prices = [bid_prices[0], ask_prices[0]]
                    flag = "flag 1"
                    self.previous_sequence = sequence_number
                    fair_value = np.mean(bid_prices + ask_prices)
                    
                    spread = max((ask_prices[0] - bid_prices[0])/2, MIN_SPREAD)
                    flag = "flag 2"
                    bid_price = intval(fair_value - spread + PRESSURE_SPREAD*self.bid_pressure)
                    ask_price = intval(fair_value + spread - PRESSURE_SPREAD*self.ask_pressure)

                    if self.count % 1 == 0:
                        string = "{}, Bid Price {}, Ask Price {}, Spread {}, Bid Pressure {}, Ask Pressure {}, Position {}".format(self.count, bid_price, ask_price, ask_price - bid_price, self.bid_pressure, self.ask_pressure, self.etf_position)
                        self.log(string)
                    self.count += 1

                    """ Decide what to do on trends """
                    if bid_price > ask_price:
                        if self.bid_pressure > self.ask_pressure:
                            # want bid pressure to push up asks
                            ask_price = intval(bid_price + 2*spread)
                        elif self.bid_pressure < self.ask_pressure:
                            # want ask pressure to push down bids
                            bid_price = intval(ask_price - 2*spread)

                    """ Decide Special High volume cases """
                    if self.bid_pressure == MIN_PRESSURE:
                        self.bid_volume = BIG_VOL
                    if self.ask_pressure == MIN_PRESSURE:
                        self.ask_volume = BIG_VOL
                        
                    flag = "flag 3"
                    if bid_price not in self.active_orders.values() and self.etf_position < HIGHEST_POSITION:
                        if len(self.bid_ids) < MAX_SIDE_ORDERS:
                            bid_id = next(self.order_ids)
                            self.bid_ids.append(bid_id)
                            self.active_orders[bid_id] = bid_price
                            self.send_insert_order(bid_id, Side.BUY, bid_price, self.bid_volume, Lifespan.GOOD_FOR_DAY)
        ##                    self.log("BID: {}, {}".format(bid_id, bid_price))
                            flag = "flag 4"
                        elif self.etf_position >= HIGHEST_POSITION:
                            if self.bid_pressure > MIN_PRESSURE:
                                self.bid_pressure -= 1
                        else:
                            bid_id = self.bid_ids.pop(0)
                            self.active_orders.pop(bid_id)
                            if bid_id in self.active_orders.keys():
                                self.send_cancel_order(bid_id)
                            if self.bid_pressure < MAX_PRESSURE:
                                self.bid_pressure += 1
                        
                    flag = "flag 5"
                    if ask_price not in self.active_orders.values():
                        flag = "flag 5.1"
                        if len(self.ask_ids) < MAX_SIDE_ORDERS and self.etf_position > -HIGHEST_POSITION:
                            flag = "flag 5.2"
                            ask_id = next(self.order_ids)
                            self.ask_ids.append(ask_id)
                            self.active_orders[ask_id] = ask_price
                            self.send_insert_order(ask_id, Side.SELL, ask_price, self.ask_volume, Lifespan.GOOD_FOR_DAY)

                        elif self.etf_position <= -HIGHEST_POSITION:
                            flag = "flag 5.3"
                            if self.ask_pressure > MIN_PRESSURE:
                                self.ask_pressure -= 1
                            
                        else:
                            flag = "flag 5.4"
                            ask_id = self.ask_ids.pop(0)
                            flag = "flag 5.4.1"
                            if ask_id in self.active_orders.keys():
                                self.active_orders.pop(ask_id)
                            flag = "flag 5.4.2"
                            self.send_cancel_order(ask_id)
                            flag = "flag 5.4.3"
                            if self.ask_pressure < MAX_PRESSURE:
                                self.ask_pressure += 1
                            

                        flag = "flag 6"   
        except:
            self.log("Flag1: " + flag)

        
    def on_order_status_message(self, client_order_id: int, fill_volume: int, remaining_volume: int, fees: int) -> None:
        """Called when the status of one of your orders changes.

        The fill_volume is the number of lots already traded, remaining_volume
        is the number of lots yet to be traded and fees is the total fees for
        this order. Remember that you pay fees for being a market taker, but
        you receive fees for being a market maker, so fees can be negative.

        If an order is cancelled its remaining volume will be zero.
        """
        flag = ''
        try:
            flag = "Flag 1"
            if remaining_volume == 0:
                if client_order_id in self.active_orders.keys():
                    self.active_orders.pop(client_order_id)
                    
                flag = "Flag 2"
                if client_order_id in self.bid_ids:
                    flag = "Flag 3"
                    self.bid_ids.remove(client_order_id)
                    flag = "Flag 4"
                    if self.bid_pressure > MIN_PRESSURE:
                        self.bid_pressure -= 1
                        flag = "Flag 5"
                elif client_order_id in self.ask_ids:
                    flag = "Flag 6"
                    self.ask_ids.remove(client_order_id)
                    flag = "Flag 7"
                    if self.ask_pressure > MIN_PRESSURE:
                        self.ask_pressure -= 1
                        flag = "Flag 8"
                else:
                    pass

        except:
            self.log("Flag 2" + flag)

    def on_position_change_message(self, future_position: int, etf_position: int) -> None:
        """Called when your position changes.

        Since every trade in the ETF is automatically hedged in the future,
        future_position and etf_position will always be the inverse of each
        other (i.e. future_position == -1 * etf_position).
        """
        flag = ""
        try:
            flag = "Flag 1"
            def intval(num):
                return int(round((num)/100)*100)
            
            self.etf_position = etf_position
            if etf_position > THRESHHOLD_POSITION:
                # Over Bought
                self.ask_pressure += RETURN_STRENGTH*intval(abs(etf_position)//THRESHHOLD_POSITION)

            elif etf_position < -THRESHHOLD_POSITION:
                # Over Sold
                self.bid_pressure += RETURN_STRENGTH*intval(abs(etf_position)//THRESHHOLD_POSITION)
                    
            flag = "Flag 2"

            if abs(etf_position) >= DUMP_POSITION:
                # To keep order count down, this is done one at a time
                if len(self.bid_ids) > 0:
                    bid_id = self.bid_ids.pop(0)
                    self.active_orders.pop(bid_id)
                    self.send_cancel_order(bid_id)
                 
                if len(self.ask_ids) > 0:
                    ask_id = self.ask_ids.pop(0)
                    if ask_id in self.active_orders.keys():
                        self.active_orders.pop(ask_id)
                    self.send_cancel_order(ask_id)
                
                if len(self.bid_ids + self.ask_ids) == 0:
                    self.bid_pressure = 0
                    self.ask_pressure = 0
                    
                    if etf_position > 0:
                        ask_id = next(self.order_ids)
                        self.ask_ids.append(ask_id)
                        self.send_insert_order(ask_id, Side.SELL, self.best_prices[1], int(abs(etf_position)), Lifespan.GOOD_FOR_DAY)
                    else:
                        bid_id = next(self.order_ids)
                        self.ask_ids.append(bid_id)
                        self.send_insert_order(bid_id, Side.BUY, self.best_prices[0], int(abs(etf_position)), Lifespan.GOOD_FOR_DAY)

            flag = "Flag 3" 
        except:
            self.log("Flag 3: " + flag)
            
    def on_trade_ticks_message(self, instrument: int, trade_ticks: List[Tuple[int, int]]) -> None:
        """Called periodically to report trading activity on the market.

        Each trade tick is a pair containing a price and the number of lots
        traded at that price since the last trade ticks message.
        """
        pass
