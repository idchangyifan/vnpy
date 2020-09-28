from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine
from vnpy.trader.ui import QtWidgets


from ..engine import (
    PosMonitor,
    APP_NAME,
)


class PosMonitorManager(QtWidgets.QWidget):
    """"""


    def __init__(self, main_engine: MainEngine, event_engine: EventEngine):
        """"""
        super().__init__()

        self.main_engine: MainEngine = main_engine
        self.event_engine: EventEngine = event_engine

        self.paper_engine: PosMonitor = main_engine.get_engine(APP_NAME)

        self.init_ui()

    def init_ui(self):
        """"""
        self.setWindowTitle("仓位监控")
        self.setFixedHeight(200)
        self.setFixedWidth(500)

        passive_leg_name = QtWidgets.QSpinBox()
        passive_leg_name.setMinimum(1)
        passive_leg_name.setValue(self.paper_engine.passive_leg_name)
        passive_leg_name.valueChanged.connect(self.paper_engine.set_passive_leg_name)

        active_leg_name = QtWidgets.QSpinBox()
        active_leg_name.setMinimum(0)
        active_leg_name.setValue(self.paper_engine.active_leg_name)
        active_leg_name.valueChanged.connect(self.paper_engine.set_active_leg_name)



        form = QtWidgets.QFormLayout()
        form.addRow("主动腿名称", active_leg_name)
        form.addRow("被动腿名称", passive_leg_name)

        vbox = QtWidgets.QVBoxLayout()
        vbox.addStretch()
        vbox.addLayout(form)
        vbox.addStretch()
        self.setLayout(vbox)
