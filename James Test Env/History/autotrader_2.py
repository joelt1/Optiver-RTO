import asyncio
import numpy as np
import itertools

from typing import List, Tuple

from ready_trader_one import BaseAutoTrader, Instrument, Lifespan, Side


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
        self.bid_volume = 1
        self.ask_volume = 1
        self.etf_position = 0


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

        try:
            fair_value = int(round((np.mean(bid_prices + ask_prices))/100)*100)
            spread = int(round((max(ask_prices[0] - bid_prices[0], MIN_SPREAD))/100)*100)
            bid_price = fair_value - spread
            ask_price = fair_value + spread
            
            if sequence_number % 100 == 0:
                string = "{}, Bid Price {}, Ask Price {}, Spread {}, Position {}".format(sequence_number, bid_price, ask_price, ask_price - bid_price, self.etf_position)
                self.log(string)
                
            if bid_price not in self.active_orders.values():
                bid_id = next(self.order_ids)
                self.bid_ids.append(bid_id)
                self.active_orders[bid_id] = bid_price
                self.send_insert_order(bid_id, Side.BUY, bid_price, self.bid_volume, Lifespan.GOOD_FOR_DAY)
                
            if ask_price not in self.active_orders.values():
                ask_id = next(self.order_ids)
                self.ask_ids.append(ask_id)
                self.active_orders[ask_id] = ask_price
                self.send_insert_order(bid_id, Side.SELL, ask_price, self.ask_volume, Lifespan.GOOD_FOR_DAY)
                
        except:
            self.log("Error 1")


        
    def on_order_status_message(self, client_order_id: int, fill_volume: int, remaining_volume: int, fees: int) -> None:
        """Called when the status of one of your orders changes.

        The fill_volume is the number of lots already traded, remaining_volume
        is the number of lots yet to be traded and fees is the total fees for
        this order. Remember that you pay fees for being a market taker, but
        you receive fees for being a market maker, so fees can be negative.

        If an order is cancelled its remaining volume will be zero.
        """
        try:
            if remaining_volume == 0:
                self.active_orders.pop(client_order_id)
                if client_order_id in self.bid_ids:
                    self.bid_ids.remove(client_order_id)
                elif client_order_id in self.ask_ids:
                    self.ask_ids.remove(client_order_id)
        except:
            self.log("Error 2")

    def on_position_change_message(self, future_position: int, etf_position: int) -> None:
        """Called when your position changes.

        Since every trade in the ETF is automatically hedged in the future,
        future_position and etf_position will always be the inverse of each
        other (i.e. future_position == -1 * etf_position).
        """
        self.etf_position = etf_position
 

    def on_trade_ticks_message(self, instrument: int, trade_ticks: List[Tuple[int, int]]) -> None:
        """Called periodically to report trading activity on the market.

        Each trade tick is a pair containing a price and the number of lots
        traded at that price since the last trade ticks message.
        """
        pass
