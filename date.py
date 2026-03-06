"""
时间管理
功能：
根据锚定日期，计算对应的数据时间。
时间输入可为时间字符串也可以是datetime
时间输出均为str
内部程序时间储存均为datetime格式
"""

import datetime
import pandas as pd
import chinese_calendar


def is_market_day(date_) -> bool:
    """
    判断是否是交易日。输入可以是datetime，也可以是时间字符串
    """
    date_ = pd.to_datetime(date_) if isinstance(date_, str) else date_
    assert isinstance(date_, datetime.datetime) or isinstance(date_,datetime.date)
    if chinese_calendar.is_workday(date_) and date_.isoweekday() in [1, 2, 3, 4, 5]:
        return True
    else:
        return False


def add_one_market_day(ref_date) -> str:
    """
    ref_date：时间字符串或者datetime
    程序返回ref_date下一个交易日期，不会对ref_date本身是否是交易日做判断
    """
    ref_date = pd.to_datetime(ref_date) if isinstance(ref_date, str) else ref_date
    assert isinstance(ref_date, datetime.datetime) or isinstance(ref_date,datetime.date)
    res_day = ref_date + datetime.timedelta(days=1)
    while not is_market_day(res_day):
        res_day = res_day + datetime.timedelta(days=1)
    return res_day.strftime('%Y%m%d')


def minus_one_market_day(ref_date) -> str:
    """
    ref_date：时间字符串或者datetime
    程序返回ref_date上一个交易日期，不会对ref_date本身是否是交易日做判断
    """
    ref_date = pd.to_datetime(ref_date) if isinstance(ref_date, str) else ref_date
    assert isinstance(ref_date, datetime.datetime) or isinstance(ref_date,datetime.date)
    res_day = ref_date - datetime.timedelta(days=1)
    while not is_market_day(res_day):
        res_day = res_day - datetime.timedelta(days=1)
    return res_day.strftime('%Y%m%d')


def add_mark_day(ref_date, n) -> str:
    """
    锚定日期增加n个交易日。n 可为负数
    """
    assert isinstance(n, int)
    ref_date = pd.to_datetime(ref_date) if isinstance(ref_date, str) else ref_date
    assert isinstance(ref_date, datetime.datetime) or isinstance(ref_date,datetime.date)
    res_day = ref_date
    if n == 0:
        return ref_date.strftime('%Y%m%d')
    elif n > 0:
        for i in range(n):
            res_day = add_one_market_day(res_day)
    else:
        for i in range(-n):
            res_day = minus_one_market_day(res_day)
    return res_day


def date_range(date_start: str = "20220426", date_end: str = "20220507"):
    res_list = []
    if is_market_day(date_start):
        res_list.append(date_start)

    next_day = add_one_market_day(date_start)
    while next_day <= date_end:
        res_list.append(next_day)
        next_day = add_one_market_day(next_day)
    return res_list


class TargetDate:
    def __init__(self, ref_date):
        """
        用锚定日期初始化
        """
        self._ref_date = self.to_date(ref_date) if isinstance(ref_date, str) else ref_date
        assert isinstance(self._ref_date, datetime.datetime) or isinstance(self._ref_date, datetime.date)

    @property
    def ref_date(self) -> str:
        return self._ref_date.strftime('%Y%m%d')

    def set_ref_date(self, ref_date):
        self._ref_date = self.to_date(ref_date) if isinstance(ref_date, str) else ref_date
        assert isinstance(self._ref_date, datetime.datetime) or isinstance(self._ref_date, datetime.date)

    @property
    def is_market_day(self):
        return is_market_day(self.ref_date)

    @staticmethod
    def to_date(date_str_) -> datetime.datetime:
        return pd.to_datetime(date_str_)

    def add_mark_day(self, n) -> str:
        """
        锚定日期增加n个交易日。n 可为负数
        """
        return add_mark_day(self.ref_date, n)


__all__ = ['is_market_day', 'add_one_market_day', 'minus_one_market_day', 'add_mark_day','TargetDate']

if __name__ == '__main__':
    minus_one_market_day(datetime.datetime.now())
    add_one_market_day(datetime.datetime.now())
    minus_one_market_day('20230113')
    add_one_market_day('20230113')
    date_str = '20230113'
    t_day = TargetDate(datetime.datetime.now())
    t_day.add_mark_day(4)
    t_day.add_mark_day(5)

    t_day = TargetDate('20230116')
    t_day.add_mark_day(4)
    t_day.add_mark_day(5)
    (t_day.add_mark_day(-5))