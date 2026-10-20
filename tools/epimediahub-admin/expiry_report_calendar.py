"""Pure Europe/Berlin calendar rules for future admin expiry reporting.

Scheduling and FCM delivery are intentionally NOT activated by importing this
module. Callers must supply verified user/playlist expiry dates; never guess.
"""
from __future__ import annotations
import calendar
from datetime import date, timedelta
from collections import defaultdict
from expiry_report_pdf import Expiry


def upcoming_month_on_last_day(today:date):
    """Return next (year, month) only on the current month's final day."""
    if type(today) is not date:
        raise ValueError("day must be a local Europe/Berlin calendar date")
    if today.day != calendar.monthrange(today.year,today.month)[1]:
        return None
    nxt=today.replace(day=1)+timedelta(days=32)
    nxt=nxt.replace(day=1)
    return (nxt.year,nxt.month)


def calendar_week_on_monday(today:date):
    """Monday-Sunday inclusive, only when the local calendar date is Monday."""
    if type(today) is not date:
        raise ValueError("day must be a local Europe/Berlin calendar date")
    if today.weekday()!=0:
        return None
    return (today,today+timedelta(days=6))


def weekly_entries(records:list[Expiry],monday:date):
    """Playlist-separated due list for the given Monday-Sunday week.

    Return safe internal structured rows, NOT a push notification payload.
    Never pass customer names to lock-screen/Firebase push messages.
    """
    if type(monday) is not date or monday.weekday()!=0:
        raise ValueError("week must begin on Monday")
    last=monday+timedelta(days=6)
    result=defaultdict(list)
    for row in records:
        if not isinstance(row,Expiry) or type(row.day) is not date:
            raise ValueError("invalid report input")
        if not isinstance(row.playlist,str) or not row.playlist.strip():
            raise ValueError("invalid playlist")
        if not isinstance(row.customer,str) or not row.customer.strip():
            raise ValueError("invalid customer")
        if monday<=row.day<=last:
            result[row.playlist].append(row)
    for rows in result.values():
        rows.sort(key=lambda row:(row.day,row.customer.casefold()))
    return dict(sorted(result.items(),key=lambda v:v[0].casefold()))
