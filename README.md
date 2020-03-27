# Optiver-RTO
Team repository for the competition. Note - certain files have not been displayed as per competition policy.


# Ready Trader One

## What is Ready Trader One?

Ready Trader One is a programming competition for University students created
by Optiver Asia Pacific Pty Ltd. The competition involves coding an Autotrader
that can trade in a simulated market, trading against other teams to deliver
the best result.

Details about the competition, including the terms and conditions, can be
found on the website: [readytraderone.com.au](https://readytraderone.com.au).

## What's in this repository?

This repository contains everything needed to run a Ready Trader One *match*
in which multiple Autotraders compete against each other in a simulated
market. For the exact definition of a match, see the competition terms and
conditions.

The repository contains:

* autotrader.json - configuration file for your Autotrader
* autotrader.py - implement your Autotrader by modifying this file
* data - sample data to use for testing your Autotrader
* example1.* - a very simple example Autotrader to help you get started
* example2.* - a slightly improved example Autotrader
* exchange.json - configuration file for the simulator
* ready_trader_one - the Ready Trader One source code
* run.py - Use this with Python 3.6 to run a match 

## Autotrader configuration

Each Autotrader is configured with a JSON file like this:

    {
      "Execution": {
        "Host": "localhost",
        "Port": 12345
      },
      "Information": {
        "AllowBroadcast": false,
        "Interface": "0.0.0.0",
        "ListenAddress": "239.255.1.1",
        "Port": 12346
      },
      "TeamName": "TraderOne",
      "Secret": "secret"
    }

The elements of the Autotrader configuration are:

* Execution - network address for sending execution requests (e.g. to place
an order)
* Information - network address to listen for information messages broadcast
by the exchange simulator
* TeamName - name of the team for this Autotrader
* Secret - password for this Autotrader

## Simulator configuration

The market simulator is configured with a JSON file called "exchange.json".
Here is an example:

    {
      "Engine": {
        "MarketDataFile": "data/day1.csv",
        "MatchEventsFile": "match_events.csv",
        "Speed": 1.0,
        "TickInterval": 0.25
      },
      "Execution": {
        "ListenAddress": "localhost",
        "Port": 12345
      },
      "Fees": {
        "Maker": -0.0001,
        "Taker": 0.0002
      },
      "Information": {
        "AllowBroadcast": false,
        "Host": "239.255.1.1",
        "Interface": "0.0.0.0",
        "Port": 12346
      },
      "Instrument": {
        "EtfClamp": 0.002,
        "TickSize": 1.00
      },
      "Limits": {
        "ActiveOrderCountLimit": 10,
        "ActiveVolumeLimit": 200,
        "MessageFrequencyInterval": 1.0,
        "MessageFrequencyLimit": 20,
        "PositionLimit": 100
      },
      "Traders": {
        "TraderOne": "secret",
        "ExampleOne": "qwerty",
        "ExampleTwo": "12345"
      }
    }

The elements of the Autotrader configuration are:

* Engine - source data file, output filename, simulation speed and tick interval
* Execution - network address to listen for Autotrader connections
* Fees - details of the fee structure
* Information - network address to broadcast information messages to Autotraders
* Instrument - details of the instrument to be traded
* Limits - details of the limits by which Autotraders must abide
* Traders - team names and secrets of the Autotraders

## Running a match

To run a match, simply execute `run.py`:

    python3.6 run.py

It will take approximately 45 minutes for the match to complete and several
files will be produced:

* `autotrader.log` - log file for your Autotrader
* `example1.log` - log file for the first example Autotrader
* `example2.log` - log file for the second example Autotrader
* `exchange.log` - log file for the simulator
* `match_events.csv` - a record of events during the match

To aid testing, you can speed up the match by modifying the "Speed" setting
in the "exchange.json" configuration file - for example, setting the speed
to 2.0 will halve the time it takes to run a match. Note, however, that
increasing the speed may change the results.

When testing your Autotrader, you should try it with different sample data
files by modifying the "MarketDataFile" setting in the "exchange.json"
file.

## Autotrader environment

Autotraders in Ready Trader One will be run in the following environment:

* Operating system: Linux
* Python version: 3.6.10
* Available libraries: numpy 1.18.1; pandas 1.0.1; scipy 1.4.1
* Memory limit: 2GB
* Total disk usage limit: 100MB (including the log file)
* Maximum number of Autotraders per match: 8
* Autotraders may not create sub-processes but may have multiple threads
* Autotraders may not access the internet

## Testing with additional Autotraders

A match will have a maximum of eight Autotraders which compete against each
other for profit. By default the simulator will run with three Autotraders:

| Team name  | Python file     | Configuration file |
| ---------- | --------------- | ------------------ |
| TraderOne  | `autotrader.py` | `autotrader.json`  |
| ExampleOne | `example1.py`   | `example1.json`    |
| ExampleTwo | `example2.py`   | `example2.json`    |

To test your Autotrader against an additional opponent:

1. Add the Python file name without the ".py" to the `trader_names` list in
`run.py`.
2. Add the team name and secret to the "Traders" section in `exchange.json`.

## How do I submit my AutoTrader?

When you registered for the competition you were given details of an SFTP
server to use for submitting your Autotrader. To submit your Autotrader
simply upload your `autotrader.py` file to the SFTP site.

You may replace your `autotrader.py` file with a new one at any time. For
each of the three online tournaments the most recent version of
`autotrader.py` in your SFTP site at the time the tournament begins will be
used. Files other than `autotrader.py` will be ignored.
