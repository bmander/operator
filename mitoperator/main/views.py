from django.http import HttpResponse

from models import StopTimeUpdate
from django.db.models import Count, Avg

from datetime import date
from time import time

from gtfs import Schedule
sched = Schedule( 'massachusetts-archiver_20110913_0233.db' )

def home(req):
    n = StopTimeUpdate.objects.all().count()
    n_trips = StopTimeUpdate.objects.values('trip_id').annotate(Count('trip_id')).count()

    delay = StopTimeUpdate.objects.filter( fetch_timestamp__gt = int(time())-60*5 ).aggregate(Avg("arrival_delay"))
    recent_count = StopTimeUpdate.objects.filter( fetch_timestamp__gt = int(time())-60*5 ).values('trip_id').annotate(Count('trip_id')).count()

    return HttpResponse( """<html><body><p>%d data points</br>
%s trips</p>
<p>
tracking %d vehicles</br>
the whole system is %.2f mins late</br>
</p>
<p><a href="http://en.wikipedia.org/wiki/Operator_(The_Matrix)">operator</a>. get me out of here.</p>
<p><a href="/mysite.fcgi/stops">stops</a></p>
</body></html>"""%(n,n_trips, recent_count, delay['arrival_delay__avg']/60.0) )

def gtfs_timestr( time ):
    return "%02d:%02d:%02d"%((time/3600)%12,(time%3600)/60,time%60)

def deviation(request):
    trip_id = request.GET['trip_id']

    stu = StopTimeUpdate.objects.all().filter(trip_id=trip_id).order_by("-fetch_timestamp")

    return HttpResponse( "<br>".join( ["%ss ago- %s"%(int(time())-x.data_timestamp, x.arrival_delay) for x in stu] ) )

def deviationrecords( request ):
    trip_id = request.GET['trip_id']

    stu = StopTimeUpdate.objects.all().filter(trip_id=trip_id).order_by("-fetch_timestamp")

    return HttpResponse( "<br>".join( ["%ss ago- %s"%(int(time())-x.data_timestamp, x.arrival_delay) for x in stu] ) )

from util import trips_on_date
def trips(request):
    stop_id = request.GET['stop_id']
    today = date.today()
    trips = list(trips_on_date( sched, today, stop_id ))

    payload = "<br>".join( ["""%s - %s - <a href="/mysite.fcgi/deviation?trip_id=%s">%s</a>"""%(str(x),gtfs_timestr(x[3]),x[5],x[5]) for x in trips] )

    return HttpResponse( """<html><body>today:%s<br><br>%s</body></html>"""%(today, payload) )

def stops(request):
    
    payload = "<br>".join( ["""<a href="/mysite.fcgi/trips?stop_id=%s">%s</a>"""%(stop.stop_id,stop.stop_name) for stop in sched.stops] ) 

    return HttpResponse( """<html><body>%s</body></html>"""%payload )
