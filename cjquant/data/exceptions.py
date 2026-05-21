class CJQuantDataError(Exception):
    pass

class DataFetchError(CJQuantDataError):
    pass

class DataFormatError(CJQuantDataError):
    pass

class AlignmentError(CJQuantDataError):
    pass