from django.http import HttpResponse
from django.shortcuts import render_to_response
from django.db.models import Count, Avg
from models import StopTimeUpdate, Stop, ServicePeriod, Trip, ServicePeriodException
from datetime import date, datetime
from time import time

import json

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

def deviationrecords( request ):

    trip_id = request.GET['trip_id']
    stus = StopTimeUpdate.objects.all().filter(trip__trip_id=trip_id).order_by("fetch_timestamp").select_related('trip')

    # buckets dict of (trip_id, start_date) -> stu
    buckets = {}

    for stu in stus:
        if (stu.trip_id, stu.start_date) not in buckets:
            buckets[(stu.trip_id, stu.start_date)] = []

        # make the stoptimeupdate into a jsonable dict
        obj = stu.to_jsonable()

        # piece together a datetime object for the moment this stoptimeupdate's trip started
        trip_start_seconds_since_midnight = stu.trip.start_time
        trip_start_hh = trip_start_seconds_since_midnight/3600
        trip_start_mm = (trip_start_seconds_since_midnight%3600)/60
        trip_start_ss = trip_start_seconds_since_midnight%60
        trip_start_year = int(stu.start_date[0:4])
        trip_start_month = int(stu.start_date[4:6])
        trip_start_day = int(stu.start_date[6:])
        trip_start_dt = datetime( trip_start_year, trip_start_month, trip_start_day, trip_start_hh, trip_start_mm, trip_start_ss )
       
        # datetime for the data
        data_dt = datetime.fromtimestamp( stu.data_timestamp )

        # time of the stoptimeupdate with respect to when the trip starts 
        time_since_trip_start = data_dt - trip_start_dt
        obj['time_since_trip_start'] = time_since_trip_start.days*24*3600 + time_since_trip_start.seconds

        buckets[(stu.trip_id, stu.start_date)].append( obj )

    return HttpResponse( json.dumps( buckets.items(), indent=2 ), mimetype="text/plain" )

def stops(request):
    stops = Stop.objects.all()

    return render_to_response( "stops.html", {'stops':stops} )

def stop(request, stop_id):
    stop = Stop.objects.get(stop_id=stop_id)

    querydate = date.today()
    dateord = querydate.toordinal()
    dow = querydate.weekday()
    dow_name = {0:'monday',1:'tuesday',2:'wednesday',3:'thursday',4:'friday',5:'saturday',6:'sunday'}[dow]

    filter_args = {dow_name:1, 'start_date__lte':dateord, 'end_date__gte':dateord}
    sps = set([x['service_id'] for x in ServicePeriod.objects.all().filter( **filter_args ).values('service_id')])

    sp_excepts = ServicePeriodException.objects.all().filter(date=dateord)
    for sp_except in sp_excepts:
        if int(sp_except.exception_type) == 1:
            sps.add( sp_except.service_period.service_id )
        elif int(sp_except.exception_type) == 2:
            sps.remove( sp_except.service_period.service_id )

    stoptimes = stop.stoptime_set.all().filter(trip__service_period__service_id__in = sps).order_by('departure_time')

    return render_to_response( "stop.html", {'stop':stop, 'stoptimes':stoptimes} )

def trip(request, trip_id):
    trip = Trip.objects.get( trip_id=trip_id )
    holidays = trip.service_period.serviceperiodexception_set.filter(exception_type='2')
    also = trip.service_period.serviceperiodexception_set.filter(exception_type='1')

    stoptimes = trip.stoptime_set.all().order_by('departure_time')

    stus = trip.stoptimeupdate_set.all().order_by('data_timestamp')
    return render_to_response( "trip.html", {'trip':trip, 'holidays':holidays, 'also':also, 'stoptimes':stoptimes, 'stus':stus} )

def recent(request):
    stus = StopTimeUpdate.objects.all().order_by("-data_timestamp")[:500]
    return render_to_response( "recent.html", {'stus':stus} )

def viz( request ):
    trips = []

    if 'trip_id' in request.GET:
        trips = [ Trip.objects.get( trip_id=request.GET['trip_id'] ) ]

    return render_to_response( "viz.html",  {'trips':trips} )
