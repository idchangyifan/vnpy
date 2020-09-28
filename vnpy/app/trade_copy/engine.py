from collections import defaultdict

from vnpy.event import Event, EventEngine
from vnpy.rpc import RpcClient, RpcServer
from vnpy.trader.event import (EVENT_POSITION, EVENT_TRADE, EVENT_TIMER, EVENT_ORDER, EVENT_LOG)

from vnpy.trader.object import OrderRequest, CancelRequest, LogData, SubscribeRequest
from ...trader.constant import OrderType, Direction, Offset, Status
from ...trader.converter import OffsetConverter
from ...trader.engine import MainEngine, BaseEngine


APP_NAME = 'TradeCopy'


class TradeCopyEngine(BaseEngine):
    """交易复制引擎"""
    MODE_PROVIDER = 1
    MODE_SUBSCRIBER = 2

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine):
        """Constructor"""
        super().__init__(main_engine, event_engine, APP_NAME)
        self.main_engine = main_engine
        self.event_engine = event_engine
        # Subscriber/Provider
        self.mode = None
        # 当前账户持仓情况,不会为负数。若开仓是多，则即便value为0，key仍然是多
        self.pos_dict = defaultdict(int)  # vt_positionid:int
        # 目标持仓情况
        self.target_dict = defaultdict(int)  # vt_positionid:int
        # 复制比例
        self.copy_ratio = 1
        # provider定时推送时间周期（秒）
        self.interval = 3
        self.subscribeSet = set()
        self.offset_converter = OffsetConverter(self.main_engine)
        # provider定时推送计数器（秒）
        self.count = 0
        # RPC Server
        self.server = None
        # RPC Client
        self.client = None
        # 注册事件驱动所需要的的回调函数
        self.register_event()

    def start_provider(self, rep_address, pub_address, interval):
        """初始化provider，绑定在ui的按钮"""
        self.mode = self.MODE_PROVIDER
        self.interval = interval

        if not self.server:
            self.server = RpcServer()
            # self.server.usePickle()
            self.server.register(self.get_pos)
            self.server.start(rep_address, pub_address)

        self.write_log('启动发布者模式（如需修改通讯地址请重启程序）')

    def start_subscriber(self, req_address, sub_address, copy_ratio):
        """初始化subscriber，绑定在ui的按钮"""
        self.mode = self.MODE_SUBSCRIBER
        self.copy_ratio = copy_ratio
        if not self.client:
            self.client = TcClient(self)
            # self.client.usePickle()
            # self.client.subscribeTopic('')
            self.client.start(req_address, sub_address)

        self.write_log('启动订阅者模式，运行时请不要执行其他交易操作')
        self.init_target()

    def stop(self):
        """停止跟单app，绑定在ui的按钮"""
        if self.client:
            self.client.stop()
            self.write_log('订阅者模式已停止')

        if self.server:
            self.server.stop()
            self.write_log('发布者模式已停止')

        self.mode = None

    def register_event(self):
        """
        将事件函数注册在event_engine，当event_engine产生相应的事件时，就会触发这些函数的调用。这里的
        EVENT_POSITION，EVENT_TRADE，EVENT_TIMER，EVENT_ORDER都是常用事件，分别为：
        1.持续获取当前持仓的on_position()，对应vnpy主界面的持仓界面，返回数据为event.data，类型为PositionData
        2.产生交易行为时触发的on_trade(), 返回数据为event.data，类型为TradeData
        3.每秒钟定时执行的on_timer()
        4.发单时的on_order(),返回数据为event.data，类型为OrderData
        """
        self.event_engine.register(EVENT_POSITION, self.process_position_event)
        self.event_engine.register(EVENT_TRADE, self.process_trade_event)
        self.event_engine.register(EVENT_TIMER, self.process_timer_event)
        self.event_engine.register(EVENT_ORDER, self.process_order_event)

    def check_and_trade(self, vt_symbol):
        """subscriber专用，检查当前是否存在尚未交易成功的order，若无，则发新单"""
        if self.check_no_working_order(vt_symbol):
            self.new_order(vt_symbol)
        else:
            self.cancel_order(vt_symbol)

    def process_timer_event(self, event):
        """provider专用，每隔interval秒执行一次，用作推送当前provider的所有持仓"""
        if self.mode != self.MODE_PROVIDER:
            return
        self.count += 1
        if self.count < self.interval:
            return
        self.count = 0
        for vt_positionid in self.pos_dict.keys():
            self.publish_pos(vt_positionid)

    def process_trade_event(self, event):
        """
        provider&subscriber公用，当产生交易事件时，更新其自己的当前仓位。provider将该合约对应仓位进行推送
        这里有个坑，刚登陆ctp账号，尚未启动trade_copy app的时候会触发此事件，所以用self.mode的
        存在性来判断是否执行过滤操作，因为此刻trade_copy app还尚未初始化
        """
        if not self.mode:
            return
        trade = event.data
        # 标准写法，要用这玩意儿必须在这儿加上这一行
        self.offset_converter.update_trade(trade)

        vt_positionid = '.'.join([trade.vt_symbol, trade.direction.value])

        if trade.offset == Offset.OPEN:
            self.pos_dict[vt_positionid] += trade.volume
        # 平仓需要额外的处理。比如假设开仓的vt_positionid为SR101.CZCE.多，平仓的vt_positionid则为SR101.CZCE.空
        # 这里是对不齐的，所以要格外处理一下
        else:
            if Direction.SHORT.value in vt_positionid:
                vt_positionid = vt_positionid.replace(Direction.SHORT.value, Direction.LONG.value)
            else:
                vt_positionid = vt_positionid.replace(Direction.LONG.value, Direction.SHORT.value)
            self.pos_dict[vt_positionid] -= trade.volume

        if self.mode == self.MODE_PROVIDER:
            self.publish_pos(vt_positionid)

    def process_position_event(self, event):
        """on_position，实时的更新当前持仓的情况，保存在pos_dict中。provider和subscriber都会用到"""
        position = event.data
        # 标准写法
        self.offset_converter.update_position(position)

        self.pos_dict[position.vt_positionid] = position.volume

    def process_order_event(self, event):
        """on_order,原方法检测到拒单时会停止整个trade_copy功能，这里感觉有待商榷"""
        order = event.data
        # 标准写法
        self.offset_converter.update_order(order)

        if order.status == Status.REJECTED:
            self.write_log('监控到委托拒单')
            # self.stop()

    def publish_pos(self, vt_positionid):
        """provider专用，根据vt_positionid索引pos_dict并进行推送"""
        pos = self.pos_dict[vt_positionid]

        l = vt_positionid.split('.')
        direction = l[-1]
        vt_symbol = vt_positionid.replace('.' + direction, '')

        data = {
            'vt_symbol': vt_symbol,
            'vt_positionid': vt_positionid,
            'pos': pos
        }
        self.server.publish('', data)

    def update_pos(self, data):
        """subscriber专用，根据收到的data更新自身仓位（pos_dict），并进行下单"""
        vt_symbol = data['vt_symbol']
        if vt_symbol not in self.subscribeSet:
            contract = self.main_engine.get_contract(vt_symbol)
            if not contract:
                return
            req = SubscribeRequest(symbol=contract.symbol, exchange=contract.exchange)
            self.main_engine.subscribe(req, contract.gateway_name)

        vt_positionid = data['vt_positionid']
        target = int(data['pos'] * self.copy_ratio)
        self.target_dict[vt_positionid] = target

        self.check_and_trade(vt_symbol)

    def new_order(self, vt_symbol):
        """subscriber专用，发送新的order"""
        for vt_positionid in self.target_dict.keys():
            if vt_symbol not in vt_positionid:
                continue

            pos = self.pos_dict[vt_positionid]
            target = self.target_dict[vt_positionid]
            # 当目标仓和现有仓一致的情况下，则跳过
            if pos == target:
                continue
            # 标准写法，获取合约信息
            contract = self.main_engine.get_contract(vt_symbol)
            # 标准写法，获取当前tick数据
            tick = self.main_engine.get_tick(vt_symbol)
            if not tick:
                return

            req = OrderRequest(symbol=contract.symbol,
                               exchange=contract.exchange,
                               type=OrderType.LIMIT,
                               volume=abs(target - pos),
                               direction=Direction.NET)

            # Open position
            if target > pos:
                req.offset = Offset.OPEN

                if Direction.LONG.value in vt_positionid:
                    req.direction = Direction.LONG
                    if tick.last_price == tick.limit_up:
                        req.price = tick.limit_up
                    else:
                        req.price = tick.ask_price_1
                elif Direction.SHORT.value in vt_positionid:
                    req.direction = Direction.SHORT
                    if tick.last_price == tick.limit_down:
                        req.price = tick.limit_down
                    else:
                        req.price = tick.bid_price_1

                self.main_engine.send_order(req, contract.gateway_name)

            # Close position
            elif target < pos:
                req.offset = Offset.CLOSE
                # 平仓时，req.direction应该和vt_positionid中的direction是相反的
                if Direction.LONG.value in vt_positionid:
                    req.direction = Direction.SHORT
                    if tick.last_price == tick.limit_down:
                        req.price = tick.limit_down
                    else:
                        req.price = tick.bid_price_1

                elif Direction.SHORT.value in vt_positionid:
                    req.direction = Direction.LONG
                    if tick.last_price == tick.limit_up:
                        req.price = tick.limit_up
                    else:
                        req.price = tick.ask_price_1

                # Use auto-convert for solving today/yesterday position problem
                # lock暂时写死为false
                req_list = self.offset_converter.convert_order_request(req, lock=False)
                for convertedReq in req_list:
                    self.main_engine.send_order(convertedReq, contract.gateway_name)

            msg = f'发出委托：{vt_symbol}，方向：{req.direction}, 开平：{req.offset}, 价格：{req.price}, 数量：{req.volume}'
            self.write_log(msg)

    def cancel_order(self, vt_symbol):
        """
        Cancel all orders of a certain vt_symbol
        """
        # 获取所有的order，标准写法
        l = self.main_engine.get_all_orders()
        for order in l:
            # 只撤销处于提交中以及未成交的order
            if order.vt_symbol == vt_symbol and (order.status == Status.SUBMITTING or order.status == Status.NOTTRADED):
                req = CancelRequest(orderid=order.orderid, symbol=order.symbol, exchange=order.exchange)
                # 这里的两个参数在新版中不存在了，也不知道有啥用，目前注释掉并没有啥问题
                # req.frontID = order.frontID
                # req.sessionID = order.sessionID
                self.main_engine.cancel_order(req, order.gateway_name)

        self.write_log(u'撤销%s全部活动中委托' % vt_symbol)

    # ----------------------------------------------------------------------
    def check_no_working_order(self, vt_symbol):
        """
        Check if there is still any working orders of a certain vt_symbol
        """
        l = self.main_engine.get_all_orders()
        for order in l:
            if order.vt_symbol == vt_symbol and (order.status == Status.SUBMITTING or order.status == Status.NOTTRADED):
                return False

        return True

    def write_log(self, msg):
        """app日志标准写法"""
        log = LogData(
            msg=msg,
            gateway_name=APP_NAME
        )
        # 向事件引擎推送日志事件
        event = Event(EVENT_LOG, log)
        self.event_engine.put(event)

    def get_pos(self):
        """
        Get current position data of provider
        """
        return dict(self.pos_dict)

    def init_target(self):
        """
        Init target data of subscriber based on position data from provider
        """
        d = self.client.get_pos()
        self.write_log(f'初始化收到的数据为：{d}')
        for vt_positionid, pos in d.items():
            l = vt_positionid.split('.')
            direction = l[-1]
            vt_symbol = vt_positionid.replace('.' + direction, '')

            data = {
                'vt_positionid': vt_positionid,
                'vt_symbol': vt_symbol,
                'pos': pos
            }
            self.update_pos(data)

        self.write_log(u'目标仓位初始化完成')


class TcClient(RpcClient):
    """"""

    def __init__(self, engine):
        """Constructor"""
        super(TcClient, self).__init__()

        self.engine = engine

    def callback(self, topic, data):
        """provider收到推送后的回调函数"""
        self.engine.update_pos(data)

