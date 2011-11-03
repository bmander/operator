from django.http import HttpResponse
from django.shortcuts import render_to_response
from django.db.models import Count, Avg
from models import StopTimeUpdate, Stop, ServicePeriod, Trip, ServicePeriodException, Route, VehicleUpdate, StopTime, ShapePoint
from datetime import date, datetime, timedelta
from time import time

from shapely.geometry import Point, LineString

import json

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
            set_vehicle_position_deviation_metadata( run.vps, shape, stoptimes )

        for run in runs:
            buckets[(run.start_date, run.trip_id)] = [(vp.percent_along_route,vp.sched_deviation) for vp in run.vps]

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

def cons(ary):
    for i in range(len(ary)-1):
        yield ary[i], ary[i+1]

def time_at_percent_along_route( stoptimes, percent_along_route ):
    stoptimes = list(stoptimes)
    if percent_along_route <= stoptimes[0].percent_along_route:
        return stoptimes[0].departure_time 
    if percent_along_route >= stoptimes[-1].percent_along_route:
        return stoptimes[-1].arrival_time
    for st1, st2 in cons( stoptimes ):
        if st1.percent_along_route <= percent_along_route and \
           st2.percent_along_route > percent_along_route:
            aa = (percent_along_route - st1.percent_along_route)/(st2.percent_along_route-st1.percent_along_route)
            return st1.arrival_time + (st2.arrival_time-st1.arrival_time)*aa

    raise Exception( "%s is not between two stoptimes %s"%(percent_along_route, [stoptime.percent_along_route for stoptime in stoptimes]) )

def trim_linestring( linestring, start ):
    """start is non-normalized distance along linestring"""

    retcoords = []
    s0 = linestring.interpolate( start )
    retcoords.append( (s0.x, s0.y) )

    for i, coord in enumerate( linestring.coords ):
        if linestring.project( Point( coord ) ) > start:
            retcoords.extend( list(linestring.coords)[i:] )
            break
   
    return LineString( retcoords )

def optimistic_project( linestring, point, normalized=False ):
    strlen = linestring.length

    segments = [LineString(pair) for pair in cons( linestring.coords )]

    curs = 0.0
    for s1, s2 in cons( segments ):
        if s1.distance( point ) < s2.distance( point ):
            ret = curs + s1.project( point )
            return ret/strlen if normalized else ret
        
        curs += s1.length

    ret = curs + s2.project( point )
    return ret/strlen if normalized else ret

def progressive_project( linestring, points, normalized=False ):
    """Assuming the linestring and points run in the same direction, project points along the line. The idea here is to gracefully handle loops in the linestring."""

    strlen = linestring.length

    curs=0.0
    for point in points:
        substring = trim_linestring( linestring, curs )
        curs += optimistic_project( substring, point )
        yield curs/strlen if normalized else curs

def pro_progressive_project( linestring, points ):
    strlen = linestring.length

    segments = [LineString(pair) for pair in cons( linestring.coords )]

    curs = 0.0
    seg = 0
    
    for point in points:

        for s1, s2 in cons( segments[seg:] ):
            if s1.distance( point ) <= s2.distance( point ):
                yield (curs + s1.project( point ))/strlen
                break

            curs += s1.length
            seg += 1
        else:
            yield (curs + s2.project( point ))/strlen
        

def set_vehicle_position_deviation_metadata( vps, shape, stoptimes ):
    # adds a 'sched_deviation' property to each vehicle position in 'vps'
    # in the process it writes all over all vps and stoptime instances

    #for stoptime, projection in zip( stoptimes, projections ):
    for stoptime in stoptimes:
        stoptime.percent_along_route = shape.project( stoptime.stop.shape, normalized=True )

    for vp in vps:
        vp.percent_along_route = shape.project( vp.shape, normalized=True )
        vp.scheduled_time =  time_at_percent_along_route( stoptimes, vp.percent_along_route ) # seconds since midnight; can go over 24 hours
        vp.scheduled_time_str = gtfs_timestr( vp.scheduled_time )

        scheduled_time_dt = build_datetime( vp.start_date, vp.scheduled_time )
         
        scheddiff  = vp.data_time - scheduled_time_dt
        vp.sched_deviation = scheddiff.days*3600*24 + scheddiff.seconds + scheddiff.microseconds/1.0e6

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
    set_vehicle_position_deviation_metadata( run.vps, shape, stoptimes )

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
