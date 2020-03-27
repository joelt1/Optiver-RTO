import pandas as pd
from scipy.stats import linregress as linreg
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
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

for match in [13, 23, 28]:
    matchname = "match" + str(match)
    stats = []

    rows = 3
    cols = 3
    figure_pl =  plt.figure(figsize = (14, 10)) #plt.subplot(nrows = rows, ncols = cols, figsize = (14, 10))

    figure_pl.subplots_adjust(left=0.08, bottom=0.07, right=0.95, top=0.90,\
                              wspace=0.17, hspace=0.31)

    gs = figure_pl.add_gridspec(3, 3)
    axes_pl_00 = figure_pl.add_subplot(gs[0, :])
    axes_pl_10 = figure_pl.add_subplot(gs[1, :])
    axes_pl_20 = figure_pl.add_subplot(gs[2, 0])
    axes_pl_21 = figure_pl.add_subplot(gs[2, 1:3])

    data = pd.read_csv(matchname + "_events.csv")

    axes_pl_10.plot(data["Time"], data["EtfPrice"])
    axes_pl_10.plot(data["Time"], data["FuturePrice"])
    axes_pl_10.legend(["ETF", "Future"], loc = "upper left")  

    traders = data["Competitor"].unique()
    for trader in traders:
        trader_data = data[data["Competitor"] == trader]
        axes_pl_20.plot(trader_data["Time"], trader_data["ProfitLoss"])
        axes_pl_21.plot(trader_data["Time"], trader_data["EtfPosition"])

        # Stats
        net_profit = trader_data["ProfitLoss"].iloc[-1]
        # Volume Filled
        inserted_volume = trader_data[trader_data["Operation"] == "Insert"]["Volume"]
        mean_inserted = np.mean(inserted_volume[inserted_volume > 0])
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

        stats.append([trader, round(mean_inserted, 2), round(mean_filled, 2), total_trades,\
                      num_wins, round(mean_wins, 2), round(p_win, 2), num_losses, round(mean_loss, 2),\
                      round(p_loss, 2)])
    labels = ["Mean Insert Vol", "Mean Fill Vol", "Total Filled Trades", "Winning Trades", "Average Win", "% Won", "Losing Trades", "Average Loss", "% Lost", "Test"]

        
    table(axes_pl_00, stats, labels) # Make Table 

    figure_pl.suptitle("Match Events")

    axes_pl_20.legend(traders, loc = "upper left")
    axes_pl_21.legend(traders, loc = "upper left")
    ##
    axes_pl_10.set_title("ETF Price")
    axes_pl_20.set_title("Profit Loss")
    axes_pl_21.set_title("Etf Position")
    ##
    axes_pl_20.set_xlabel("Time")
    axes_pl_21.set_xlabel("Time")


    ##    plt.pause(0.1)
    stats = []
    plt.savefig(matchname + '/MatchEvents.png')
    plt.clf()



