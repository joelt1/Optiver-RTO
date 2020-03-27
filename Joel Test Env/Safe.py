import asyncio
import numpy as np
import itertools

from typing import List, Tuple

from ready_trader_one import BaseAutoTrader, Instrument, Lifespan, Side

MIN_SPREAD = 50 # This is the spread for each side of fair value (TESTVAL = 50)
PRESSURE_SPREAD = 50 # Degree to which pressure is added. (TESTVAL = 50)
MAX_SIDE_ORDERS = 4 # Dont let this go higher than 4 else  no room for cancels (TESTVAL = 4)
SET_VOLUME = 3 #(TESTVAL = 2) If we can increase the volume without increasing volitility, then we can increase our score
BIG_VOL = 3 # For stable markets (TESTVAL = 3)
BIG_PRESSURE = -2 # Pressure value for BIG_VOL to occur (TESTVAL = -2)
MIN_PRESSURE = -2 # (TESTVAL = -2) Negative value allows us to take advantage of large spreads in the market when safe
MAX_PRESSURE = 100 # Just incase things break and the pressure goes too far up
HIGHEST_POSITION = 10 # If etf_position exceeds this, we start adding pressure to return to 0
RETURN_STRENGTH = 10 # When etf_position != 0, we push it back towards 0 with this value. Be careful of it being to strong
DUMP_POSITION = 50 # This was remade to be a boundry. If etf_position approaches this, prices will be made to be soo competitive that it they must be sold.



class AutoTrader(BaseAutoTrader):
    def __init__(self, loop: asyncio.AbstractEventLoop):
        """Initialise a new instance of the AutoTrader class."""
        super(AutoTrader, self).__init__(loop)
        # Define basic variables
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

##        self.previous_sequence = 0
##        self.best_prices = [0, 0]

        # Used for tracking information
        self.bid_count = 1
        self.bid_acceptance = 1
        self.bid_cancels = 1
        self.ask_count = 1
        self.ask_acceptance = 1
        self.ask_cancels = 1

    def log(self, line):
        """ Log Activities in seperate log file """
        pass
        
    def on_error_message(self, client_order_id: int, error_message: bytes) -> None:
        """Called when the exchange detects an error.

        If the error pertains to a particular order, then the client_order_id
        will identify that order, otherwise the client_order_id will be zero.
        """
        """ Optivers Code throws back cross order error messages, even though there are
            none. The orders till go through though so Im silencing the error on our logs.
            It will still appear in optivers logs through. """

        try:
            if "cross" in str(error_message):
                pass
            elif "order count" in str(error_message):
                bid_id = self.bid_ids.pop(0)
                if bid_id in self.active_orders.keys():
                    self.active_orders.pop(bid_id)
                self.send_cancel_order(bid_id)

                ask_id = self.ask_ids.pop(0)
                if ask_id in self.active_orders.keys():
                    self.active_orders.pop(ask_id)
                self.send_cancel_order(ask_id)
                
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

        """ The bid and ask pressure shift the bid and ask prices towards values where they will be
            accepted by the market. When a transaction does occur, the pressure decreases and prices
            become less competitive. When no transaction occurs, Pressure increases.
            There is some pressure adjustment due to the value of the etf position, but the main
            influence of the etf position is considered seperately due to the Pressure being very slow
            to respond to changes in position.

            The main idea I found is that the most successful auto-traders aim to keep the etf-position
            around zero by pricing their bids and asks correctly rather than using logic statements. By
            adding pressure onto the prices, the prices will only be as competitive as they need to be.



            Flags are used for debugging"""
        flag = ''
        try:
            if instrument == Instrument.FUTURE:
                flag = "flag 0"
                def intval(num):
                    return int(round((num)/100)*100)

                # I dont want any trades to occur if etf_position gets too high. While the bot freezes here, we wont be booted from the match and will still be scored.
                if bid_prices[0] != 0 and ask_prices[0] != 0 and abs(self.etf_position) < 90:
##                    self.best_prices = [bid_prices[0], ask_prices[0]]
                    flag = "flag 1"
                    
                    fair_value = np.mean(bid_prices + ask_prices) # Approximate Fair Value
                    spread = max((ask_prices[0] - bid_prices[0])/2, MIN_SPREAD) # Approximate spread

                    """ This bit here reacts weekly when our etf_position is low but pushes very strongly when it starts getting too high """
                    if self.etf_position > 0:
                        resistance = 10/(DUMP_POSITION - self.etf_position)**2
                    else:
                        resistance = -10/(-DUMP_POSITION + self.etf_position)**2

                    # Prices are adjusted by the pressure of the trades and by how far the etf_position is from zero. 
                    bid_price = intval(fair_value - spread + PRESSURE_SPREAD*self.bid_pressure - RETURN_STRENGTH*self.etf_position + resistance)
                    ask_price = intval(fair_value + spread - PRESSURE_SPREAD*self.ask_pressure - RETURN_STRENGTH*self.etf_position - resistance)
                    
                    flag = "flag 2"
                    if self.count % 100 == 0:
                        # Record stuff relevant to monitaring the performance of the bot
                        string = "{}, Bid Acceptance {:.2f}, Ask Acceptance {:.2f}, Spread {}, Bid Pressure {}, Ask Pressure {}, Position {}".format(self.count, (self.bid_acceptance/self.bid_cancels), (self.ask_acceptance/self.ask_cancels), ask_price - bid_price, self.bid_pressure, self.ask_pressure, self.etf_position)
                        self.log(string)
                        
                    if self.count % 100 == 0:
                        # Reset the measures so they remain sensitive
                        self.bid_count = 1
                        self.bid_acceptance = 1
                        self.bid_cancels = 1
                        self.ask_count = 1
                        self.ask_acceptance = 1
                        self.ask_cancels = 1
                        
                    self.count += 1
                    """ Decide what to do on trends """
                    # Bid price > ask Price occurs when the bids have been pushed up more than the asks, or where the asks have been pushed down more than the bids
                    if bid_price >= ask_price:
                        if self.bid_pressure > self.ask_pressure:
                            # Up Trend
                            # want bid pressure to push up asks
                            ask_price = intval(bid_price + 2*spread)
                            self.bid_pressure -= 1
                        elif self.bid_pressure < self.ask_pressure:
                            # Down Trend
                            # want ask pressure to push down bids
                            bid_price = intval(ask_price - 2*spread)
                            self.ask_pressure -= 1

                    """ Decide Special High volume cases """
                    if self.bid_pressure <= BIG_PRESSURE and self.ask_pressure <= BIG_PRESSURE:
                        # In Easy Markets, the volume can be increased, but Im wary about this control at the moment
                        self.bid_volume = BIG_VOL
                        self.ask_volume = BIG_VOL
                        
                    flag = "flag 3"
                    if bid_price not in self.active_orders.values(): # Check if bid_price has been recorded. Used for checking for wash trades. This is where optiver goes wrong.
                        if len(self.bid_ids) < MAX_SIDE_ORDERS:
                            bid_id = next(self.order_ids)
                            self.bid_ids.append(bid_id)
                            self.active_orders[bid_id] = bid_price
                            self.send_insert_order(bid_id, Side.BUY, bid_price, self.bid_volume, Lifespan.GOOD_FOR_DAY)
                            self.bid_count += 1
        ##                    self.log("BID: {}, {}".format(bid_id, bid_price))
                            flag = "flag 4"
                        elif self.etf_position >= HIGHEST_POSITION:
                            # Add extra pressure due to etf_position
                            if self.bid_pressure > MIN_PRESSURE:
                                self.bid_pressure -= 1
                            if self.ask_pressure < MAX_PRESSURE:
                                self.ask_pressure += 1
                        else:
                            bid_id = self.bid_ids.pop(0)
                            self.active_orders.pop(bid_id)
                            if bid_id in self.active_orders.keys():
                                self.active_orders.pop(bid_id)
                            self.send_cancel_order(bid_id)
                            if self.bid_pressure < MAX_PRESSURE:
                                self.bid_pressure += 1
                            
                            self.bid_cancels += 1
                        
                    flag = "flag 5"
                    if ask_price not in self.active_orders.values():
                        flag = "flag 5.1"
                        if len(self.ask_ids) < MAX_SIDE_ORDERS:
                            flag = "flag 5.2"
                            ask_id = next(self.order_ids)
                            self.ask_ids.append(ask_id)
                            self.active_orders[ask_id] = ask_price
                            self.send_insert_order(ask_id, Side.SELL, ask_price, self.ask_volume, Lifespan.GOOD_FOR_DAY)
                            self.ask_count += 1
                        elif self.etf_position <= -HIGHEST_POSITION:
                            flag = "flag 5.3"
                            if self.ask_pressure > MIN_PRESSURE:
                                self.ask_pressure -= 1
                            if self.bid_pressure < MAX_PRESSURE:
                                self.bid_pressure += 1
                            
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
                            
                            self.ask_cancels += 1
                            

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
                # Decrease Pressure on successful trades
                if client_order_id in self.active_orders.keys():
                    self.active_orders.pop(client_order_id)
                    
                flag = "Flag 2"
                if client_order_id in self.bid_ids:
                    flag = "Flag 3"
                    self.bid_ids.remove(client_order_id)
                    flag = "Flag 4"
                    if self.bid_pressure > MIN_PRESSURE:
                        self.bid_pressure -= 1
                    self.bid_acceptance += 1
                    flag = "Flag 5"
                elif client_order_id in self.ask_ids:
                    flag = "Flag 6"
                    self.ask_ids.remove(client_order_id)
                    flag = "Flag 7"
                    if self.ask_pressure > MIN_PRESSURE:
                        self.ask_pressure -= 1
                    self.ask_acceptance += 1
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
##            def intval(num):
##                return int(round((num)/100)*100)
##            
            self.etf_position = etf_position # Update etf position


##""" I havent managed to implement this part properly, but I dont think we should get to this point due to resistance pressure defined above """
##            if abs(etf_position) >= 90:
##                # To keep order count down, this is done one at a time
##                if len(self.bid_ids) > 0:
##                    bid_id = self.bid_ids.pop(0)
##                    self.active_orders.pop(bid_id)
##                    self.send_cancel_order(bid_id)
##                 
##                if len(self.ask_ids) > 0:
##                    ask_id = self.ask_ids.pop(0)
##                    if ask_id in self.active_orders.keys():
##                        self.active_orders.pop(ask_id)
##                    self.send_cancel_order(ask_id)
##                
##                if len(self.bid_ids + self.ask_ids) == 0:
##                    self.bid_pressure = 0
##                    self.ask_pressure = 0
##                    
##                    if etf_position > 0:
##                        ask_id = next(self.order_ids)
##                        self.ask_ids.append(ask_id)
##                        self.send_insert_order(ask_id, Side.SELL, self.best_prices[1], int(abs(etf_position)), Lifespan.GOOD_FOR_DAY)
##                    else:
##                        bid_id = next(self.order_ids)
##                        self.ask_ids.append(bid_id)
##                        self.send_insert_order(bid_id, Side.BUY, self.best_prices[0], int(abs(etf_position)), Lifespan.GOOD_FOR_DAY)

            flag = "Flag 3" 
        except:
            self.log("Flag 3: " + flag)
            
    def on_trade_ticks_message(self, instrument: int, trade_ticks: List[Tuple[int, int]]) -> None:
        """Called periodically to report trading activity on the market.

        Each trade tick is a pair containing a price and the number of lots
        traded at that price since the last trade ticks message.
        """
        pass
