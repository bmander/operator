from django.http import HttpResponse
from django.shortcuts import render_to_response
from django.db.models import Count, Avg
from django.core.cache import cache
from models import StopTimeUpdate, Stop, ServicePeriod, Trip, ServicePeriodException, Route, VehicleUpdate, StopTime, ShapePoint, TripSpeedStats
from datetime import date, datetime, timedelta
from time import time

from shapely.geometry import Point, LineString

import json

from util import build_datetime, Measurer

from scipy.stats.mstats import mquantiles
import numpy

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

def is_number_junk(num):
    #return abs(num)<1E-6 or abs(num)>1E6 or numpy.isnan(num)
    return abs(num)>1E10 or numpy.isnan(num)

def _differentiate(ary):
    for i in range(len(ary)-1):
        if ary[i+1] is None or ary[i] is None:
            yield None
        else:
            yield ary[i+1]-ary[i]

def _collect_trip_stats( trip, measurer, fittype ):
    print "collect trip stats"

    run_data = []

    print "get all vehicle updates for this trip"
    vps = trip.vehicleupdate_set.all().order_by('data_timestamp')
    if len(vps)==0:
        return None
    print "done"

    runs = trip.trip_runs
    shape = trip.shape

    shapelen = measurer.measure( trip.shape )

    first_stoptime = trip.stoptime_set.all().order_by("stop_sequence")[0]

    print "set vehicle distance along route for each run"
    for run in runs:
        print "run %s"%run
        run.set_vehicle_dist_along_route( shape, shapelen, first_stoptime )
    print "done"

    print "set vehicle speed for each run along route"
    resolution=40
    run_speeds = []
    run_accels = []
    for run in runs:
        print "run %s"%run
        run_speed = list(run.get_dist_speed(shapelen, resolution=resolution))
        run_accel = [x/resolution if x is not None else None for x in _differentiate(run_speed)]
        run_data.append( [run.start_date, 
                          list(run.clean_vehicle_position_stream()),
                          (resolution,run_speed),
                          (resolution,run_accel)] )

        run_speeds.append( run_speed )
        run_accels.append( run_accel )
    print "done"

    mean_speed = []
    if fittype=="gamma":
        print "fit gamma dist for each point along route"
        fit_params = []
        if len(run_speeds)==0 or len(run_speeds[0])==0:
            return None
        for i in range(len(run_speeds[0])):
            print "%s/%s"%(i,len(run_speeds[0]))
            col = [row[i] for row in run_speeds if row[i] is not None]

            print "fitting..."
            fit_alpha, fit_loc, fit_beta = gamma.fit( col )
            print "done"
            if not (is_number_junk(fit_alpha) or is_number_junk(fit_loc) or is_number_junk(fit_beta)):
                print "getting ppfs (%s %s %s)..."%(fit_alpha, fit_loc, fit_beta)
                fa,fb,fc=(gamma.ppf(0.05, fit_alpha, fit_loc, fit_beta),
                          gamma.ppf(0.5, fit_alpha, fit_loc, fit_beta),
                          gamma.ppf(0.95, fit_alpha, fit_loc, fit_beta))
                print "done"
                if numpy.isnan(fa) or numpy.isnan(fb) or numpy.isnan(fc):
                    mean_speed.append( (None, None, None) )
                    fit_params.append( (None, None, None) )
                else:
                    mean_speed.append( (fa,fb,fc) )
                    fit_params.append( (fit_alpha, fit_loc, fit_beta) )
            else:
                mean_speed.append( (None, None, None) )
                fit_params.append( (None, None, None) )
        print "done"

        # stow fit params for later use
        vsr,created = TripSpeedStats.objects.get_or_create(trip=trip) 
        vsr.stats = json.dumps( ['gamma',resolution,fit_params] )
        vsr.save()
    elif fittype=='uniform':
        print "fit uniform dist for each point along route"
        fit_params = []
        if len(run_speeds)==0 or len(run_speeds[0])==0:
            return None
        for i in range(len(run_speeds[0])):
            print "%s/%s"%(i,len(run_speeds[0]))
            col = [row[i] for row in run_speeds if row[i] is not None]
            if len(col)==0:
                mean_speed.append( (None, None, None) )
                fit_params.append( (None, None, None, None, None) )
            else:
                q1,q2,q3,q4,q5 = mquantiles(col, [0.16666666666,0.333333333,0.5,0.666666666,0.8333333333])
                mean_speed.append( (min(col), q3, max(col)) )
                fit_params.append( (min(col),q1,q2,q3,q4,q5,max(col)) )

        print "done"

        # stow fit params for later use
        vsr,created = TripSpeedStats.objects.get_or_create(trip=trip) 
        vsr.stats = json.dumps( ['uniform',resolution,fit_params] )
        vsr.save()

    return {'trip_id':trip.trip_id, 'run_data':run_data, 'mean_speed':[resolution,mean_speed]}

def gpsdistances( request ):
    print "GOT"

    trip = Trip.objects.get(trip_id=request.GET['trip_id'])
    fittype = request.GET.get('fittype', 'gamma')

    print request.GET

    if request.GET.get( 'nocache' )=='true':
        trip_stats = _collect_trip_stats( trip, Measurer(), fittype )
    else:
        trip_stats = cache.get('tripstats_%s'%trip.trip_id)

        if trip_stats is None:
            trip_stats = _collect_trip_stats( trip, Measurer(), fittype )
            cache.set('tripstats_%s'%trip.trip_id, trip_stats, 3600*24)

    return HttpResponse( json.dumps( trip_stats, indent=2 ), mimetype="text/plain" ) 

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
    trip_id = request.GET['trip_id']
    nocache=request.GET.get('nocache')
    fittype=request.GET.get('fittype')

    return render_to_response( "gpsdistviz.html",  {'trip_id':trip_id,'nocache':nocache,'fittype':fittype} )

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

def _speedsamples( disttype, params, n=1 ):
    if disttype=='gamma':
        samples = [gamma.rvs(a,b,c,size=n) if (a and b and c) else [None]*n for a,b,c, in params]
    elif disttype=='uniform':
        samples = []
        for uniparams in params:
            sample=[]
            for i in range(n):
                nquads = len(uniparams)-1
                quad = numpy.random.randint(nquads)
                sinstance = numpy.random.uniform( uniparams[quad],uniparams[quad+1] )
                sample.append( sinstance if not numpy.isnan(sinstance) else None )
            samples.append( sample )
    else:
        samples=[]

    return samples
    return HttpResponse( json.dumps([resolution,samples]) )

def speedsamples( request ):
    tripstats = TripSpeedStats.objects.get( trip__pk=request.GET['trip_id'] )
    disttype, resolution, params = tripstats.stats_obj
    samples = [x[0] for x in _speedsamples(disttype, params,n=1)]

    return HttpResponse( json.dumps([resolution,samples]) )

def pathsamples( request ):
    n_samples = 60
    min_v = 0.1 #m/s

    tripstats = TripSpeedStats.objects.get( trip__pk=request.GET['trip_id'] )
    disttype, resolution, gamma_params = tripstats.stats_obj
    #samples = [list(gamma.rvs(a,b,c,size=n_samples)) if (a and b and c) else [None]*n_samples for a,b,c in gamma_params]
    samples = _speedsamples(disttype,gamma_params,n=n_samples)

    t0 = float(request.GET['tt'])
    d0 = float(request.GET['dd'])

    paths = []

    for j in range(n_samples):
        path=[]

        # first point on the future path is the point that's given
        path.append( (d0,t0) )

        # second point
        init_i = int(d0/resolution)
        v = max( samples[init_i][j], min_v )
        dd = resolution-(d0-init_i*resolution)
        dt = dd/v # v = d/t -> t = d/v
        path.append( ((init_i+1)*resolution, t0+dt) )

        # all subsequent points
        t_cur = t0+dt
        for i in range(init_i+1,len(samples)):
            v = max( samples[i][j], min_v )
            dt = resolution/v
            t_cur += dt
            path.append( ((i+1)*resolution,t_cur) )

        paths.append( path )

    low=[]
    mid=[]
    high=[]
    n_samples = len(paths[0])
    for i in range(n_samples):
        sample = [path[i] for path in paths]
        dd = sample[0][0]
        tts = [x[1] for x in sample]

        qlow, qmid, qhigh = mquantiles( tts, prob=(0.05,0.5,0.95) )
        low.append( (dd,qlow) )
        mid.append( (dd,qmid) )
        high.append( (dd,qhigh) )

    return HttpResponse( json.dumps([paths,[low,mid,high]]) )
