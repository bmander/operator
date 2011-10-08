from django.http import HttpResponse
from django.shortcuts import render_to_response

from models import StopTimeUpdate
from django.db.models import Count, Avg

from datetime import date, datetime
from time import time

import json
from django.core import serializers

from util import trips_on_date, get_trip

from gtfs import Schedule
sched = Schedule( 'massachusetts-archiver_20110913_0233.db' )

def home(req):
    n = StopTimeUpdate.objects.all().count()

    #delay = StopTimeUpdate.objects.filter( fetch_timestamp__gt = int(time())-60*5 ).aggregate(Avg("arrival_delay"))

    #print delay

    last_update = StopTimeUpdate.objects.all().order_by( "-data_timestamp" )[1]
    last_update_dt = datetime.fromtimestamp( last_update.data_timestamp )

    #recent_count = StopTimeUpdate.objects.filter( fetch_timestamp__gt = int(time())-60*5 ).values('trip_id').annotate(Count('trip_id')).count()

    #"""%(n,n_trips, recent_count, delay['arrival_delay__avg']/60.0) )
    return render_to_response( "home.html", {'n':n, 'last_update_dt':last_update_dt } )

def gtfs_timestr( time ):
    return "%02d:%02d:%02d"%((time/3600),(time%3600)/60,time%60)

def deviation(request):
    trip_id = request.GET['trip_id']

    stu = StopTimeUpdate.objects.all().filter(trip_id=trip_id).order_by("-fetch_timestamp")

    return HttpResponse( "<br>".join( ["%ss ago- %s"%(int(time())-x.data_timestamp, x.arrival_delay) for x in stu] ) )

def deviationrecords( request ):
    trip_id = request.GET['trip_id']

    trip = get_trip( sched, trip_id )
    trip_start = trip.stop_times[0].departure_time.val
    stus = StopTimeUpdate.objects.all().filter(trip_id=trip_id).order_by("fetch_timestamp")

    records = []
    rec = []

    # scan along the list of stoptimeupdates with a given trip_id. whenever there's a big jump in the timestamp we assume we've stopped seeing STUs from one day and started seeing them for the next day. This assumes that a trip started on one day will never run at the same time as a trip started the next. This is almost certainly true for MBTA but is not true for Amtrak, for example, where STUs will hopefully be disambiguated by vehicle.
    last = None
    for stu in stus:
        jsonstu = stu.to_jsonable()
        dt = datetime.fromtimestamp( stu.data_timestamp )
        #print dt, jsonstu['arrival_delay']
        since_midnight = dt.hour*3600+dt.minute*60+dt.second
        since_trip_start = since_midnight-trip_start
        jsonstu['since_trip_start'] = since_trip_start

        if last is None:
            rec.append( jsonstu )
            last = stu
            continue
        
        #the gap is somewhat arbirarily three hours
        if stu.data_timestamp-last.data_timestamp > 3*3600:
            records.append( rec )
            rec = []

        rec.append( jsonstu )
        last = stu

    if last is not None:
        records.append( rec )

    json_serializer = serializers.get_serializer("json")()
    return HttpResponse( json.dumps( records ) )

def trips(request):
    stop_id = request.GET['stop_id']
    today = date.today()
    trips = list(trips_on_date( sched, today, stop_id ))

    payload = "<br>".join( ["""%s - %s - <a href="/mysite.fcgi/deviation?trip_id=%s">%s</a>"""%(str(x),gtfs_timestr(x[3]),x[5],x[5]) for x in trips] )

    return HttpResponse( """<html><body>today:%s<br><br>%s</body></html>"""%(today, payload) )

def stops(request):
    
    payload = "<br>".join( ["""<a href="/mysite.fcgi/trips?stop_id=%s">%s</a>"""%(stop.stop_id,stop.stop_name) for stop in sched.stops] ) 

    return HttpResponse( """<html><body>%s</body></html>"""%payload )
