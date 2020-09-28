from vnpy.app.spread_trading.backtesting import BacktestingEngine
from vnpy.app.spread_trading.strategies.garch_strategy import (
    GarchStrategy
)
from vnpy.app.spread_trading.strategies.statistical_arbitrage_strategy import StatisticalArbitrageStrategy
from vnpy.app.spread_trading.base import LegData, SpreadData
from datetime import datetime
spread = SpreadData(
    name="IH-Spread",
    legs=[LegData("IH666.CFFEX"), LegData("IH668.CFFEX")],
    price_multipliers={"IH666.CFFEX": 1, "IH668.CFFEX": -1},
    trading_multipliers={"IH666.CFFEX": 1, "IH668.CFFEX": -1},
    active_symbol="IH666.CFFEX",
    inverse_contracts={"IH666.CFFEX": False, "IH668.CFFEX": False},
    min_volume=1
)


engine = BacktestingEngine()
engine.set_parameters(
    spread=spread,
    interval="1m",
    start=datetime(2018, 10, 1),
    end=datetime(2020, 11, 10),
    rate=0.25/10000,
    slippage=0.2,
    size=300,
    pricetick=0.2,
    capital=700000,
)
# engine.set_parameters(
#     spread=spread,
#     interval="1m",
#     start=datetime(2018, 10, 1),
#     end=datetime(2020, 11, 10),
#     rate=1/10000,
#     slippage=1,
#     size=10,
#     pricetick=1,
#     capital=700000,
# )
setting = {'lambda1': 1.4075, 'lambda2': -0.8329, 'lambda3': 2.9983}
engine.add_strategy(StatisticalArbitrageStrategy, {})

engine.load_data()
engine.run_backtesting()
df = engine.calculate_result()
engine.calculate_statistics()
engine.show_chart()






