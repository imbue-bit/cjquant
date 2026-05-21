class CJQuantTradeError(Exception):
    pass

class InsufficientCashError(CJQuantTradeError):
    pass

class InsufficientPositionError(CJQuantTradeError):
    pass