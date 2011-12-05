from django.http import HttpResponse
from django.shortcuts import render_to_response
from django.db.models import Count, Avg
from models import StopTimeUpdate, Stop, ServicePeriod, Trip, ServicePeriodException, Route, VehicleUpdate, StopTime, ShapePoint
from datetime import date, datetime, timedelta
from time import time

from shapely.geometry import Point, LineString

import json

from util import build_datetime, Measurer

def home(req):
    #n = StopTimeUpdate.objects.all().count()
    n = None

    #delay = StopTimeUpdate.objects.filter( fetch_timestamp__gt = int(time())-60*5 ).aggregate(Avg("arrival_delay"))

    #print delay

    #last_update = StopTimeUpdate.objects.all().order_by( "-data_timestamp" )[1]
    #last_update_dt = datetime.fromtimestamp( last_update.data_timestamp )
    last_update_dt = None

    #recent_count = StopTimeUpdate.objects.filter( fetch_timestamp__gt = int(time())-60*5 ).values('trip_id').annotate(Count('trip_id')).count()

    #"""%(n,n_trips, recent_count, delay['arrival_delay__avg']/60.0) )
    return render_to_response( "home.html", {'n':n, 'last_update_dt':last_update_dt } )

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

        trip_start_dt = build_datetime( stu.start_date, stu.trip.start_time )
       
        # datetime for the data
        data_dt = datetime.fromtimestamp( stu.data_timestamp )

        # time of the stoptimeupdate with respect to when the trip starts 
        time_since_trip_start = data_dt - trip_start_dt
        obj['time_since_trip_start'] = time_since_trip_start.days*24*3600 + time_since_trip_start.seconds

        buckets[(stu.trip_id, stu.start_date)].append( obj )

    return HttpResponse( json.dumps( buckets.items(), indent=2 ), mimetype="text/plain" )

def group( ary, key ):
    ret = {}
    for item in ary:
        if key(item) not in ret:
            ret[key(item)] = []
        ret[key(item)].append( item )
    return ret

def gpsdeviations( request ):
    buckets = {}

    if 'trip_id' in request.GET:
        trips = [Trip.objects.get(trip_id=request.GET['trip_id'])]
    elif 'shape_id' in request.GET:
        trips = Trip.objects.all().filter(shape_id=request.GET['shape_id'])
    else:
        trips = []

    for trip in trips:

        vps = trip.vehicleupdate_set.all().order_by('data_timestamp')
        if len(vps)==0:
            continue

        runs = trip.trip_runs
        stoptimes = trip.stoptime_set.all().order_by("departure_time")
        shape = trip.shape

        for run in runs:
            run.set_vehicle_position_deviation_metadata( shape, stoptimes )

        for run in runs:
            buckets[(run.start_date, run.trip_id)] = [(vp.percent_along_route,vp.sched_deviation) for vp in run.vps]

    return HttpResponse( json.dumps( buckets.items(), indent=2 ), mimetype="text/plain" ) 

def _mean(ary):
    ary = filter( lambda x:x, ary )#filter out Nones
    if len(ary)==0:
        return None
    return float(sum(ary))/len(ary)

def _stddev(ary, mean):
    devsq = [(x-mean)**2 for x in ary if x is not None]

    if len(devsq)==0:
        return None
    
    return (float(sum(devsq))/len(devsq))**0.5

from scipy.stats import gamma

def gpsdistances( request ):
    trip_data = []

    if 'trip_id' in request.GET:
        trips = [Trip.objects.get(trip_id=request.GET['trip_id'])]
    elif 'shape_id' in request.GET:
        trips = Trip.objects.all().filter(shape_id=request.GET['shape_id'])
    else:
        trips = []

    measurer = Measurer()

    for trip in trips:
        run_data = []

        vps = trip.vehicleupdate_set.all().order_by('data_timestamp')
        if len(vps)==0:
            continue

        runs = trip.trip_runs
        shape = trip.shape

        shapelen = measurer.measure( trip.shape )

        first_stoptime = trip.stoptime_set.all().order_by("stop_sequence")[0]

        for run in runs:
            run.set_vehicle_dist_along_route( shape, shapelen, first_stoptime )

        resolution=40
        run_speeds = []
        for run in runs:
            run_speed = list(run.get_dist_speed(shapelen, resolution=resolution))
            run_data.append( [run.start_date, 
                              list(run.clean_vehicle_position_stream()),
                              (resolution,run_speed)] )

            run_speeds.append( run_speed )

        mean_speed = []
        if len(run_speeds)==0 or len(run_speeds[0])==0:
            continue
        for i in range(len(run_speeds[0])):
            col = [row[i] for row in run_speeds]
            #mean = _mean(col)
            #stddev = _stddev(col, mean)
            #mean_speed.append( (mean,stddev) )

            fit_alpha, fit_loc, fit_beta = gamma.fit( [x for x in col if x is not None] )
            mean_speed.append( (gamma.ppf(0.05, fit_alpha, fit_loc, fit_beta),
                                gamma.ppf(0.5, fit_alpha, fit_loc, fit_beta),
                                gamma.ppf(0.95, fit_alpha, fit_loc, fit_beta) ) )

        trip_data.append( {'trip_id':trip.trip_id, 'run_data':run_data, 'mean_speed':[resolution,mean_speed]} )

    return HttpResponse( json.dumps( trip_data, indent=2 ), mimetype="text/plain" ) 

def stops(request):
    stops = Stop.objects.all().select_related( 'trip' )

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

    stoptimes = stop.stoptime_set.all().filter(trip__service_period__service_id__in = sps).order_by('departure_time').select_related( 'trip' )

    return render_to_response( "stop.html", {'stop':stop, 'stoptimes':stoptimes} )

def cons(ary):
    for i in range(len(ary)-1):
        yield ary[i], ary[i+1]

def trip(request, trip_id):
    trip = Trip.objects.get( trip_id=trip_id )
    holidays = trip.service_period.serviceperiodexception_set.filter(exception_type='2')
    also = trip.service_period.serviceperiodexception_set.filter(exception_type='1')

    stoptimes = trip.stoptime_set.all().order_by('departure_time').select_related( 'stop' )

    stu_count = trip.stoptimeupdate_set.all().count()

    start_dates = VehicleUpdate.objects.all().filter(trip__pk=trip_id).values('start_date').distinct().order_by('start_date').annotate(ct=Count("start_date"))

    return render_to_response( "trip.html", {'trip':trip, 'holidays':holidays, 'also':also, 'stoptimes':stoptimes, 'stu_count':stu_count, 'start_dates':start_dates} )

def run(request, trip_id, start_date):
    run = VehicleUpdate.runs( trip_id, start_date )[0]

    trip = run.trip
    stoptimes = trip.stoptime_set.all().order_by('departure_time').select_related( 'stop' )
    shape = trip.shape
    run.set_vehicle_position_deviation_metadata( shape, stoptimes )

    return render_to_response( 'run.html', {'vps':run.vps} )

def shape(request, shape_id):
    points = ShapePoint.shape_points( shape_id )

    start_dates = VehicleUpdate.objects.all().filter(trip__shape_id=shape_id).values('trip__pk','start_date').distinct().order_by('trip__pk','start_date')

    if request.GET.get('format')=='kml':
        return render_to_response( "shape.kml", {'points':points,'shape_id':shape_id}, mimetype="text/plain" )
        
    return render_to_response( "shape.html", {'points':points,'shape_id':shape_id,'start_dates':start_dates} )

def recent(request):
    stus = StopTimeUpdate.objects.all().order_by("-data_timestamp")[:500]
    return render_to_response( "recent.html", {'stus':stus} )

def viz( request ):
    trips = []

    if 'trip_id' in request.GET:
        trips = [ Trip.objects.get( trip_id=request.GET['trip_id'] ) ]

    if 'route_id' in request.GET:
        route = Route.objects.get(route_id=request.GET['route_id'])
        for trip in route.trip_set.all().order_by('trip_headsign', 'service_period'):
            trips.append( trip )

    return render_to_response( "viz.html",  {'trips':trips} )

def gpsviz( request ):
    trips = []
    shapes = []

    if 'trip_id' in request.GET:
        trips = [ Trip.objects.get( trip_id=request.GET['trip_id'] ) ]
        shapes = [ trips[0].shape_id ]

    if 'route_id' in request.GET:
        route = Route.objects.get(route_id=request.GET['route_id'])
        shapes = set()
        for trip in route.trip_set.all().order_by('shape_id', 'trip_headsign', 'service_period'):
            trips.append( trip )
            shapes.add( trip.shape_id )

    return render_to_response( "gpsviz.html",  {'trips':trips, 'shapes':shapes} )

def gpsdistviz( request ):
    trips = []
    shapes = []

    if 'trip_id' in request.GET:
        trips = [ Trip.objects.get( trip_id=request.GET['trip_id'] ) ]
        shapes = [ trips[0].shape_id ]

    if 'route_id' in request.GET:
        route = Route.objects.get(route_id=request.GET['route_id'])
        shapes = set()
        for trip in route.trip_set.all().order_by('shape_id', 'trip_headsign', 'service_period'):
            trips.append( trip )
            shapes.add( trip.shape_id )

    return render_to_response( "gpsdistviz.html",  {'trips':trips, 'shapes':shapes} )

def routes( request ):
    routes = Route.objects.all()

    return render_to_response( "routes.html", {'routes':routes} )

def route( request, route_id ):
    route = Route.objects.get(route_id=route_id)
    trips = route.trip_set.order_by('trip_headsign', 'service_period')

    return render_to_response( "route.html", {'route':route, 'trips':trips} )

def positions( request ):
    vps = VehicleUpdate.objects.all().filter(trip__isnull=False).order_by("-data_timestamp")[:500]
    return render_to_response( "positions.html", {'vps':vps} )

def find_stddev( ary ):
    mean = sum(ary)/float(len(ary))
    square_variances = [(x-mean)**2 for x in ary]
    
    return (sum(square_variances)/float(len(ary)))**0.5

def stoptime( request, id ):
    stoptime = StopTime.objects.get(pk=id)

    runs = VehicleUpdate.runs( stoptime.trip_id )
  
    events = []
    for run in runs:
        for vu1, vu2 in cons( run.vps ):
            if vu1.percent_along_trip <= stoptime.percent_along_trip and \
               vu2.percent_along_trip >= stoptime.percent_along_trip:
                dt = vu2.data_timestamp - vu1.data_timestamp
                ds = vu2.percent_along_trip - vu1.percent_along_trip

                ds_prime = stoptime.percent_along_trip - vu1.percent_along_trip
               
                if ds == 0:
                    percent_of_interval = 1
                else:
                    percent_of_interval = ds_prime/ds

                interpolated_time = percent_of_interval*dt + vu1.data_timestamp

                events.append( {'vu1':vu1, 'vu2':vu2, 'time':datetime.fromtimestamp(interpolated_time),'timestamp':interpolated_time} )

    #meantime = sum([x['timestamp'] for x in events])/len(events)
    #stddev = find_stddev( [x['timestamp'] for x in events] )

    return HttpResponse( render_to_response( "stoptime.html", {'stoptime':stoptime, 'events':events} ) )
