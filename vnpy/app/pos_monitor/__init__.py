from pathlib import Path

from vnpy.trader.app import BaseApp

from .engine import PosMonitor, APP_NAME


class PaperAccountApp(BaseApp):
    """"""
    app_name = APP_NAME
    app_module = __module__
    app_path = Path(__file__).parent
    display_name = "仓位监控"
    engine_class = PosMonitor
    widget_name = "PosMonitor"
    icon_name = "paper.ico"