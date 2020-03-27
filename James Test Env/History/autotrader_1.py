import asyncio
import numpy as np
import itertools

from typing import List, Tuple

from ready_trader_one import BaseAutoTrader, Instrument, Lifespan, Side

MIN_SPREAD = 100
SPREAD_SHIFT = 100
MAX_VOLUME = 2
GREAT_VOL = 5
MAX_SIDE_ORDERS = 4 # Do not go over 4 else will be booted
MAX_POSITION = 10
MIN_PRESSURE = -4 # Want to add a small negative pressure to direct competitiveness
EXTREME_POSITION = 60
savefile = open("logs.txt", "w")
savefile.close()

print("Ready Trader One")
class AutoTrader(BaseAutoTrader):
    def __init__(self, loop: asyncio.AbstractEventLoop):
        """Initialise a new instance of the AutoTrader class."""
        super(AutoTrader, self).__init__(loop)
        self.bid_ids = []
        self.ask_ids = []
        self.can_place_order = True
        self.etf_position = 0
        self.order_ids = itertools.count(1)
        self.bid_pressure = 0
        self.ask_pressure = 0
        self.orders = {}
        self.best_prices = [0, 0]
        self.count = 0
        self.bid_volume = MAX_VOLUME
        self.ask_volume = MAX_VOLUME

    def log(self, line):
        try:
            print(line)
            savefile = open("logs.txt", "a+")
            savefile.write(line + '\n')
            savefile.close()
        except:
            print("Error in message")
        
    def on_error_message(self, client_order_id: int, error_message: bytes) -> None:
        """Called when the exchange detects an error.

        If the error pertains to a particular order, then the client_order_id
        will identify that order, otherwise the client_order_id will be zero.
        """
        self.log(error_message)
        self.logger.warning("error with order %d: %s", client_order_id, error_message.decode())
        self.on_order_status_message(client_order_id, 0, 0, 0)

    def on_order_book_update_message(self, instrument: int, sequence_number: int, ask_prices: List[int],
                                     ask_volumes: List[int], bid_prices: List[int], bid_volumes: List[int]) -> None:
        """Called periodically to report the status of an order book.

        The sequence number can be used to detect missed or out-of-order
        messages. The five best available ask (i.e. sell) and bid (i.e. buy)
        prices are reported along with the volume available at each of those
        price levels.
        """
        flag1 = ''
        try:
            if instrument == Instrument.FUTURE:
                self.count += 1
                flag1 = "Flag 1"
                if bid_prices[0] != 0 and ask_prices[0] != 0 :
                    self.best_prices[0] = bid_prices[0]
                    self.best_prices[1] = ask_prices[0]
                    
                    fair_value = (bid_prices[0] + ask_prices[0])/2
                    spread = max((ask_prices[0] - bid_prices[0])/2, MIN_SPREAD)

                    bid_price = int(round((fair_value - spread + SPREAD_SHIFT*self.bid_pressure)/100)*100)
                    sell_price = int(round((fair_value + spread - SPREAD_SHIFT*self.ask_pressure)/100)*100)
                    if self.count % 1 == 0:
                        string = "{}, Bid {}, Offer {}, Spread {}, Bid Pressure {}, Ask Pressure {}, Position {}".\
                              format(self.count, bid_price, sell_price, sell_price - bid_price, self.bid_pressure, self.ask_pressure, self.etf_position)
                        self.log(string)
                        
                    flag1 = "Flag 2"
                    if bid_price >= sell_price:
                        flag1= "Flag 2.1"
                        if self.bid_pressure > self.ask_pressure:
                            # Up Market
                            # want the high bid price to push up the sell price
                            self.bid_pressure -= 1
                            sell_price = int(round((bid_price + MIN_SPREAD)/100)*100) 
                        else:
                            # Down Market
                            # want the low sell price to push down the bid price
                            self.ask_pressure -= 1
                            bid_price = int(round((sell_price - MIN_SPREAD)/100)*100)
                            
                    flag1 = "Flag 2.2"    
                    if bid_price < sell_price:
                        if self.bid_pressure <= -4:
                            self.bid_volume = GREAT_VOL
                        if self.ask_pressure <= -4:
                            self.ask_volume = GREAT_VOL

                        flag1 = "Flag 3"
                        if bid_price not in self.orders.values():
                            if len(self.bid_ids) <= MAX_SIDE_ORDERS and self.etf_position < EXTREME_POSITION:
                                bid_id = next(self.order_ids)
                                self.bid_ids.append(bid_id)
                                self.orders[bid_id] = bid_price
                                self.send_insert_order(bid_id, Side.BUY, bid_price, self.bid_volume , Lifespan.GOOD_FOR_DAY)
                            elif self.etf_position > EXTREME_POSITION:
                                self.bid_pressure -= 1
                                self.ask_pressure += 1
                            else:
                                self.bid_pressure += 1
                                bid_id = self.bid_ids.pop(0)
                                self.orders.pop(bid_id)
                                self.send_cancel_order(bid_id)

                        flag1 = "Flag 4"
                        if sell_price not in self.orders.values():
                            if len(self.ask_ids) <= MAX_SIDE_ORDERS and self.etf_position > -EXTREME_POSITION:
                                ask_id = next(self.order_ids)
                                self.ask_ids.append(ask_id)
                                self.orders[ask_id] = sell_price
                                self.send_insert_order(ask_id, Side.SELL, sell_price, self.ask_volume, Lifespan.GOOD_FOR_DAY)
                            elif self.etf_position < -EXTREME_POSITION:
                                self.bid_pressure += 1
                                self.ask_pressure -= 1
                            else:
                                self.ask_pressure += 1
                                ask_id = self.bid_ids.pop(0)
                                self.orders.pop(ask_id)
                                self.send_cancel_order(ask_id)
                            flag1 = "Flag 5"
                flag1 = "Flag 6"
                
            else:
                pass
        except:
            self.log("Flag 1: " + flag1)

        
    def on_order_status_message(self, client_order_id: int, fill_volume: int, remaining_volume: int, fees: int) -> None:
        """Called when the status of one of your orders changes.

        The fill_volume is the number of lots already traded, remaining_volume
        is the number of lots yet to be traded and fees is the total fees for
        this order. Remember that you pay fees for being a market taker, but
        you receive fees for being a market maker, so fees can be negative.

        If an order is cancelled its remaining volume will be zero.
        """
        flag = ""
        try:
            flag = "flag 1"
            if remaining_volume == 0:
                if client_order_id in self.bid_ids:
                    flag = "flag 2"
                    self.bid_ids.remove(client_order_id)
                    self.orders.pop(client_order_id)
                    if self.bid_pressure > MIN_PRESSURE:
                        self.bid_pressure -= 1
                    flag = "flag 3"
                        
                elif client_order_id in self.ask_ids:
                    flag = "flag 4"
                    self.ask_ids.remove(client_order_id)
                    self.orders.pop(client_order_id)
                    if self.ask_pressure > MIN_PRESSURE:
                        self.ask_pressure -= 1
                    flag = "flag 5"
        except:
            self.log("Flag 2: " + flag)

    def on_position_change_message(self, future_position: int, etf_position: int) -> None:
        """Called when your position changes.

        Since every trade in the ETF is automatically hedged in the future,
        future_position and etf_position will always be the inverse of each
        other (i.e. future_position == -1 * etf_position).
        """
        flag = ''
        try:
            self.etf_position = etf_position

            flag = "flag 1"
            if etf_position > MAX_POSITION:
                flag = "flag 2"
                self.ask_pressure += (etf_position//MAX_POSITION)**2
                self.ask_volume += 1
            elif etf_position < -MAX_POSITION:
                flag = "flag 3"
                self.bid_pressure += (etf_position//MAX_POSITION)**2
                self.bid_volume += 1
            else:
                flag = "flag 4"
                if self.bid_volume > MAX_VOLUME:
                    self.bid_volume = MAX_VOLUME
                elif self.ask_volume > MAX_VOLUME:
                    self.ask_volume = MAX_VOLUME
            flag = "flag 5"

            if etf_position > 80:
                flag = "flag 6"
                for i in self.bid_ids + self.ask_ids:
                    self.send_cancel_order(i)
                    self.orders.pop(i)
                flag = "flag 7"
                ask_id = next(self.order_ids)
                self.ask_ids.append(ask_id)
                self.send_insert_order(ask_id, Side.SELL, self.best_prices[1], int(abs(etf_position)), Lifespan.GOOD_FOR_DAY)
                self.bid_pressure = 0
                self.ask_pressure = 0
                self.bid_ids = []
                self.ask_ids = []
                flag = "flag 8"
                
        
            elif etf_position < -80:
                flag = "flag 9"
                for i in self.ask_ids + self.bid_ids:
                    self.send_cancel_order(i)
                    self.orders.pop(i)
                flag = "flag 10"
                bid_id = next(self.order_ids)
                self.bid_ids.append(bid_id)
                self.send_insert_order(bid_id, Side.BUY, self.best_prices[0], int(abs(etf_position)), Lifespan.GOOD_FOR_DAY)
                self.bid_pressure = 0
                self.ask_pressure = 0
                self.bid_ids = []
                self.ask_ids = []
                flag = "flag 11"
        except:
            self.log("Flag 3: " + flag)

    def on_trade_ticks_message(self, instrument: int, trade_ticks: List[Tuple[int, int]]) -> None:
        """Called periodically to report trading activity on the market.

        Each trade tick is a pair containing a price and the number of lots
        traded at that price since the last trade ticks message.
        """
        pass
