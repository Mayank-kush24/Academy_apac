"""
Format datetimes for API responses as dd-mm-yyyy HH:MM:SS in IST.
Stored values are UTC; converted to Indian Standard Time (UTC+5:30) for display.
"""
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))


def format_datetime_utc(ts):
    """
    Return timestamp as string 'dd-mm-yyyy HH:MM:SS' in IST.
    Assumes stored value is UTC; converts to IST then formats.
    """
    if ts is None:
        return None
    if getattr(ts, 'tzinfo', None) is not None:
        utc = ts.astimezone(timezone.utc)
    else:
        utc = ts.replace(tzinfo=timezone.utc)
    ist = utc.astimezone(IST)
    return ist.strftime('%d-%m-%Y %H:%M:%S')
