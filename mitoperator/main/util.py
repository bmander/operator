
from datetime import date, datetime, timedelta

def gtfs_timestr( time ):
    return "%02d:%02d:%02d"%((time/3600),(time%3600)/60,time%60)

def build_datetime( datestr, timesecs ):
    # datestr is a date string like "20112901" and timesecs is the number of seconds since midnight on that date
        
    hh = int(timesecs)/3600
    mm = (int(timesecs)%3600)/60
    ss = int(timesecs)%60
    us = int((timesecs%1)*1e6)
    year = int(datestr[0:4])
    month = int(datestr[4:6])
    day = int(datestr[6:])

    #sometimes trip_start_hh is greater than 23
    extra_days = hh/24
    hh = hh%24
    ret = datetime( year, month, day, hh, mm, ss, us )
    ret += timedelta(days=extra_days)

    return ret

def cons(ary):
    for i in range(len(ary)-1):
        yield ary[i], ary[i+1]

from pyproj import Geod

class Measurer:
    def __init__(self, ellps="clrk66"):
        self.geod = Geod( ellps=ellps )

    def measure(self, shape):
        ret = 0
        for pt1, pt2 in cons( shape.coords ):
            try:
                azm1, azm2, dist = self.geod.inv( pt1[0], pt1[1], pt2[0], pt2[1] )
            except ValueError:
                continue
            ret += dist
        return ret

        
