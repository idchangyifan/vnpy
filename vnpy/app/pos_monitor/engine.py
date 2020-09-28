from collections import defaultdict
from copy import copy
from typing import Any, Dict, Tuple, Optional
from datetime import datetime
from tzlocal import get_localzone
from vnpy.trader.converter import OffsetConverter

from vnpy.event import Event, EventEngine
from vnpy.trader.utility import extract_vt_symbol, save_json, load_json
from vnpy.trader.engine import BaseEngine, MainEngine
from vnpy.trader.object import (
    OrderRequest, CancelRequest, SubscribeRequest,
    ContractData, OrderData, TradeData, TickData,
    LogData, PositionData
)
from vnpy.trader.event import (
    EVENT_ORDER,
    EVENT_TRADE,
    EVENT_TICK,
    EVENT_POSITION,
    EVENT_CONTRACT,
    EVENT_LOG,
    EVENT_TIMER
)
from vnpy.trader.constant import (
    Status,
    OrderType,
    Direction,
    Offset
)

LOCAL_TZ = get_localzone()
APP_NAME = "PosMonitor"


class PosMonitor(BaseEngine):
    setting_filename = "pos_monitor_setting.json"

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine):
        """Constructor"""
        super().__init__(main_engine, event_engine, APP_NAME)
        self.main_engine = main_engine
        self.event_engine = event_engine
        self.offset_converter = OffsetConverter(self.main_engine)
        self.pos_dict = defaultdict(int)
        self.active_leg_pos = 0
        self.passive_leg_pos = 0
        self.passive_leg_name = ''
        self.active_leg_name = ''

        self.load_setting()
        # 注册事件驱动所需要的的回调函数
        self.register_event()

    def process_position_event(self, event):
        """on_position，实时的更新当前持仓的情况，保存在pos_dict中。provider和subscriber都会用到"""
        position = event.data
        # 标准写法
        self.offset_converter.update_position(position)
        self.pos_dict[position.vt_positionid] = position.volume

    def process_timer_event(self, event):
        pass

    def register_event(self):
        """
        """
        self.event_engine.register(EVENT_POSITION, self.process_position_event)
        self.event_engine.register(EVENT_TIMER, self.process_timer_event)

    def set_passive_leg_name(self, passive_leg_name):
        self.passive_leg_name = passive_leg_name
        self.save_setting()

    def set_active_leg_name(self, active_leg_name):
        self.active_leg_name = active_leg_name
        self.save_setting()

    def save_setting(self):
        setting = {
            "passive_leg_name": self.passive_leg_name,
            "active_leg_name": self.active_leg_name,
        }
        save_json(self.setting_filename, setting)

    def load_setting(self) -> None:
        """"""
        setting = load_json(self.setting_filename)

        if setting:
            self.passive_leg_name = setting["passive_leg_name"]
            self.active_leg_name = setting["active_leg_name"]
