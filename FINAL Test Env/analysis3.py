import pandas as pd
from scipy.stats import linregress as linreg
import matplotlib.pyplot as plt
from collections import defaultdict
import numpy as np

def table(axes, stats, col_labels):
    axes.axis('tight')
    row_labels = []
    
    for i in range(len(stats)):
        row_labels.append(stats[i].pop(0))

    axes.axis('off')
    table = axes.table(stats, loc = 'center left', colLabels = col_labels, rowLabels = row_labels)
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1, 2)

data = pd.read_csv("match_events.csv")
traders = data["Competitor"].unique()

for trader in traders:
    trader_data = data[data["Competitor"] == trader]
    
    rows = 2
    cols = 3
    figure_pl, axes_pl = plt.subplots(nrows = rows, ncols = cols, figsize = (18, 8))
#
    axes_pl[0][0].plot(data["Time"], data["EtfPrice"], c = 'b')
    axes_pl[0][0].plot(data["Time"], data["FuturePrice"], c = 'r')

    time = trader_data["Time"]
    profit = trader_data["ProfitLoss"]
    position = trader_data["EtfPosition"]
    axes_pl[0][0].scatter(time, trader_data["Price"], marker = '+', c = 'g')
    
    # Stats
    net_profit = trader_data["ProfitLoss"].iloc[-1]
    # Volume Filled
    inserted_volume = trader_data[trader_data["Operation"] == "Insert"]["Volume"]
    mean_inserted = np.mean(inserted_volume[inserted_volume != 0])
    filled_volume = trader_data[trader_data["Operation"] == "Fill"]["Volume"]
    mean_filled = np.mean(filled_volume[filled_volume != 0])

    # Profitable Trades
    wins = []
    losses = []
    filled_data =  trader_data[trader_data["Operation"] == "Fill"]["ProfitLoss"]
    for i in range(1,len(filled_data)):
        diff = filled_data.iloc[i] - filled_data.iloc[i - 1]
        if diff > 0:
            wins.append(diff)
        else:
            losses.append(diff)

    num_wins = len(wins)
    mean_wins = np.mean(wins)
    num_losses = len(losses)
    mean_loss = np.mean(losses)
    total_trades = num_wins + num_losses
    p_win = 100*num_wins/total_trades if total_trades > 0 else 0
    p_loss = 100*num_losses/total_trades if total_trades > 0 else 0

    expec = (sum(wins) + sum(losses))/total_trades if total_trades > 0 else 0

    row_labels = ["Mean Insert Vol", "Mean Fill Vol", "Total Filled Trades", "Winning Trades", "Average Win", "% Won", "Losing Trades", "Average Loss", "% Lost"]
    stat = [round(mean_inserted, 2), round(mean_filled, 2), total_trades,\
                  num_wins, round(mean_wins, 2), round(p_win, 2), num_losses, round(mean_loss, 2),\
                  round(p_loss, 2)]
    stats = []
    for i in stat:
        stats.append([i])
    
    axes_pl[0][2].axis('tight')
    axes_pl[0][2].axis('off')
    axes_pl[0][2].table(stats, rowLabels = row_labels, loc = 'center right', colWidths = [1/2])
    
    axes_pl[1][2].plot(time, trader_data["BuyVolume"])
    axes_pl[1][2].plot(time, trader_data["SellVolume"])
    axes_pl[1][2].legend(["Buy Volume", "Sell Volume"])
    axes_pl[1][2].set_title("Cumulative Volume Traded")

    diff = trader_data["Price"] - trader_data["EtfPrice"]
    diff = diff[diff != 0]
    
    axes_pl[0][1].hist(diff , bins = np.arange(-10.5, 10.5, 1))
    axes_pl[0][1].set_xlim([-10, 10])
    axes_pl[0][1].set_xticks(np.arange(-10, 11, 2))
    
    axes_pl[1][0].plot(time, profit)
    axes_pl[1][1].plot(time, position)

    figure_pl.suptitle(trader)
    axes_pl[0][0].legend(["ETF", "Future", "Traded Price"], loc = "upper left")    
    axes_pl[0][0].set_title("ETF Price")
    
    axes_pl[0][1].set_title("Price - EtfPrice (Diff != 0)")
    axes_pl[1][0].set_title("Profit Loss")
    axes_pl[1][1].set_title("Etf Position")

    axes_pl[1][0].set_xlabel("Time")
    axes_pl[1][1].set_xlabel("Time")
##        plt.show()
    plt.savefig("match_analysis/" + trader + 'Perfomance.png')
    figure_pl.clear()
    plt.close(figure_pl)
















