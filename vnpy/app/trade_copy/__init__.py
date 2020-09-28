from pathlib import Path
from vnpy.trader.app import BaseApp
from .engine import TradeCopyEngine, APP_NAME


class TradeCopyApp(BaseApp):
    """"""
    app_name = 'APP_NAME'
    app_module = __module__
    app_path = Path(__file__).parent
    display_name = "交易复制"
    engine_class = TradeCopyEngine
    widget_name = "TradeCopyManager"
    icon_name = "rm.ico"
