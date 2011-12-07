from django.db import models
from datetime import datetime

from util import build_datetime, gtfs_timestr

# Create your models here.

class Info( models.Model ):
    timestamp = models.IntegerField() 
    buspos_timestamp = models.IntegerField()

class StopTimeUpdate(models.Model):
    trip = models.ForeignKey("Trip", db_column="trip_id")
    start_date = models.CharField(max_length=200)

    stop_sequence = models.IntegerField(null=True)
    stop_id = models.CharField(max_length=200)
    arrival_delay = models.IntegerField(null=True)
    arrival_time = models.IntegerField(null=True)
    arrival_uncertainty = models.IntegerField(null=True)
    departure_delay = models.IntegerField(null=True)
    departure_time = models.IntegerField(null=True)
    departure_uncertainty = models.IntegerField(null=True)
    schedule_relationship = models.CharField(max_length=200)

    fetch_timestamp = models.IntegerField()
    data_timestamp = models.IntegerField()

    @property 
    def data_time( self ):
        return datetime.fromtimestamp( self.data_timestamp )

    def to_jsonable( self ):
        ret = {}
        ret['trip_id'] = self.trip_id
        ret['start_date'] = self.start_date
        ret['stop_sequence'] = self.stop_sequence
        ret['stop_id'] = self.stop_id
        ret['arrival_delay'] = self.arrival_delay
        ret['arrival_time'] = self.arrival_time
        ret['arrival_uncertainty'] = self.arrival_uncertainty
        ret['departure_delay'] = self.departure_delay
        ret['departure_time'] = self.departure_time
        ret['departure_uncertainty'] = self.departure_uncertainty
        ret['schedule_relationship'] = self.schedule_relationship
        ret['fetch_timestamp'] = self.fetch_timestamp
        ret['data_timestamp'] = self.data_timestamp

        return ret;

def cons(ary):
    for i in range(len(ary)-1):
        yield ary[i], ary[i+1]

class Run:
    """a collection of vehicle updates with the same trip_id and start_date"""

    def __init__(self, trip_id, start_date):
        self.trip_id = trip_id
        self.start_date = start_date
        self.vps = []

    def add(self, vp):
        self.vps.append( vp ) 

    @property
    def trip(self):
        return Trip.objects.get(trip_id=self.trip_id)

    def _time_at_percent_along_route( self, stoptimes, percent_along_route ):
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

    def set_vehicle_position_deviation_metadata( self, shape, stoptimes ):
        # adds a 'sched_deviation' property to each vehicle position in 'vps'
        # in the process it writes all over all vps and stoptime instances

        for stoptime in stoptimes:
            stoptime.percent_along_route = shape.project( stoptime.stop.shape, normalized=True )

        for vp in self.vps:
            vp.percent_along_route = shape.project( vp.shape, normalized=True )
            vp.scheduled_time = self._time_at_percent_along_route( stoptimes, vp.percent_along_route ) # seconds since midnight; can go over 24 hours
            vp.scheduled_time_str = gtfs_timestr( vp.scheduled_time )

            scheduled_time_dt = build_datetime( vp.start_date, vp.scheduled_time )
             
            scheddiff  = vp.data_time - scheduled_time_dt
            vp.sched_deviation = scheddiff.days*3600*24 + scheddiff.seconds + scheddiff.microseconds/1.0e6

    def set_vehicle_dist_along_route( self, shape, shapelen, first_stoptime ):

        scheduled_start_dt = build_datetime( self.start_date, first_stoptime.departure_time )

        for vp in self.vps:
            scheddiff  = vp.data_time - scheduled_start_dt
            vp.time_since_start = scheddiff.days*3600*24 + scheddiff.seconds + scheddiff.microseconds/1.0e6

            vp.percent_along_route = shape.project( vp.shape, normalized=True )
            vp.dist_along_route = vp.percent_along_route*shapelen

    def clean_vehicle_position_stream( self ):
        # starts the stream at the last global minimum of distance_along_route; thereafter, only yields points where the distance_along_route is larger or equal to the previous distance_along_route

        vps = [(vp.time_since_start, vp.data_timestamp,vp.dist_along_route,vp.percent_along_route) for vp in self.vps]

        dists = [vp[2] for vp in vps]

        min_dist_along_route = min( dists )
        max_dist_along_route = max( dists )

        # find first instance of the min dist, scanning backwards; this is where things start
        for i, dist in enumerate(reversed(dists)):
            if dist==min_dist_along_route:
                start_point = len(vps)-(i+1)
                break

        # find first instances of max dist, scanning forwards; this is where things end
        end_point = dists.index( max_dist_along_route )+1

        last_dist = -1000000

        for vp in vps[start_point:end_point]:
            if vp[2] >= last_dist:
                yield vp
                last_dist = vp[2]

    def _resample( self, vps, x_min, x_max, resolution ):
        x_sample = 0
        segment_ix = 0
        while x_sample <= x_max:
            vp2_x=None
            for (vp1_t, vp1_x), (vp2_t, vp2_x) in cons( vps[segment_ix:] ):
                if x_sample < vp1_x:
                    yield (None, x_sample)
                    break

                if x_sample >= vp1_x and x_sample < vp2_x:
                    
                    dx = (vp2_x-vp1_x)
                    dt = (vp2_t-vp1_t)
                    if dt==0:
                        continue

                    t_sample = ((x_sample-vp1_x)/dx)*dt + vp1_t

                    yield (t_sample, x_sample)
                    break

                segment_ix += 1

            if x_sample > vp2_x or vp2_x is None:
                yield (None, x_sample)

            x_sample += resolution


    def get_dist_speed( self, shapelen, resolution=40 ):
        # make sure to sun set_vehicle_dist_along_route beforehand

        vps = [(time_since_start, dist_along_route) for time_since_start, data_timestamp, dist_along_route, percent_along_route in self.clean_vehicle_position_stream()]

        #resample VPS at given resolution
        resampled_vps = list(self._resample( vps, 0, shapelen, resolution ))

        for (vp1_t, vp1_x), (vp2_t, vp2_x) in cons(resampled_vps):
            if vp1_t is None or vp2_t is None:
                yield None
            else:
                yield (vp2_x-vp1_x)/(vp2_t-vp1_t)


class VehicleUpdate(models.Model):
    trip = models.ForeignKey("Trip", db_column="trip_id", null=True)
    start_date = models.CharField(max_length=200, null=True)
    schedule_relationship = models.CharField(max_length=200, null=True)

    latitude = models.FloatField(null=True)
    longitude = models.FloatField(null=True)

    current_stop_sequence = models.IntegerField(null=True)
    data_timestamp = models.IntegerField(null=True)

    fetch_timestamp = models.IntegerField(null=True)
    percent_along_trip = models.FloatField(null=True)

    @property 
    def data_time( self ):
        return datetime.fromtimestamp( self.data_timestamp )

    @property
    def shape(self):
        return Point( self.longitude, self.latitude )

    @classmethod
    def runs(cls, trip_id, start_date=None):
        filters = {}
        filters['trip__pk']=trip_id
        if start_date is not None:
            filters['start_date']=start_date
        trip_vehicle_updates = cls.objects.all().filter(**filters).order_by('data_timestamp')

        ret = {}
        for vehicle_update in trip_vehicle_updates:
            if vehicle_update.start_date not in ret:
                ret[vehicle_update.start_date] = Run( trip_id, vehicle_update.start_date )

            ret[vehicle_update.start_date].add( vehicle_update )

        return ret.values()

class Agency( models.Model ):
    class Meta:
        managed = False
        db_table = "agency"

    agency_id = models.CharField( max_length = 200, primary_key=True )
    agency_name = models.CharField( max_length = 200 )
    agency_url = models.CharField( max_length = 200 )
    agency_timezone = models.CharField( max_length = 200 )
    agency_lang = models.CharField( max_length = 200 )
    agency_phone = models.CharField( max_length = 200 )

from datetime import date
class ServicePeriod( models.Model ):
    class Meta:
        managed = False
        db_table = "calendar"

    service_id = models.CharField( max_length = 200, primary_key=True )
    monday = models.IntegerField()
    tuesday = models.IntegerField()
    wednesday = models.IntegerField()
    thursday = models.IntegerField()
    friday = models.IntegerField()
    saturday = models.IntegerField()
    sunday = models.IntegerField()
    start_date = models.IntegerField()
    end_date = models.IntegerField()

    def __repr__(self):
        return "<ServicePeriod %s %s%s%s%s%s%s%s %s %s>"%(self.service_id, self.monday, self.tuesday, self.wednesday, self.thursday, self.friday, self.saturday, self.sunday, date.fromordinal( self.start_date), date.fromordinal( self.end_date ))

    def __str__(self):
        return repr(self)

class ServicePeriodException( models.Model ):
    class Meta:
        managed = False
        db_table = "calendar_dates"

    service_period = models.ForeignKey( ServicePeriod, db_column="service_id" )
    date = models.IntegerField()
    exception_type = models.CharField( max_length = 5 )

    @property
    def date_date(self):
        return date.fromordinal( self.date )

class Route( models.Model ):
    class Meta:
        managed = False
        db_table = "routes"

    route_id = models.CharField( max_length = 200, primary_key=True )
    agency = models.ForeignKey( Agency, db_column="agency_id" )
    route_short_name = models.CharField( max_length = 200 )
    route_long_name = models.CharField( max_length = 500 )
    route_desc = models.TextField()
    route_type = models.IntegerField()
    route_url = models.URLField()
    route_color = models.CharField( max_length=200 )
    route_text_color = models.CharField( max_length = 200 )
    
class Stop( models.Model ):
    class Meta:
        managed = False
        db_table = "stops"

    stop_id = models.CharField( max_length = 200, primary_key=True )
    stop_code = models.CharField( max_length = 200 )
    stop_name = models.TextField()
    stop_desc = models.TextField()
    stop_lat = models.FloatField()
    stop_lon = models.FloatField()
    zone_id = models.CharField( max_length=200 )
    stop_url = models.URLField()
    location_type = models.CharField( max_length=200 )
    parent_station = models.CharField( max_length=200 )

    @property
    def shape(self):
        return Point( self.stop_lon, self.stop_lat )

class ShapePoint( models.Model ):
    class Meta:
        managed = False
        db_table = "shapes"

    shape_id = models.CharField( max_length=200 )
    shape_pt_lat = models.CharField( max_length=200 )
    shape_pt_lon = models.CharField( max_length=200 )
    shape_pt_sequence = models.IntegerField()
    shape_dist_traveled = models.CharField( max_length=200 )

    @classmethod
    def shape_points(cls, shape_id):
        return cls.objects.all().filter( shape_id=shape_id ).order_by('shape_pt_sequence')

    @classmethod
    def shape(cls, shape_id):
        return LineString( [(float(x.shape_pt_lon),float(x.shape_pt_lat)) for x in cls.shape_points(shape_id)] )

from shapely.geometry import LineString, Point
class Trip( models.Model ):
    class Meta:
        managed = False
        db_table = "trips"

    route = models.ForeignKey( Route, db_column="route_id" )
    service_period = models.ForeignKey( ServicePeriod, db_column="service_id" )
    trip_id = models.CharField( max_length=200, primary_key=True )
    trip_headsign = models.CharField( max_length=200 )
    trip_short_name = models.CharField( max_length = 200 )
    direction_id = models.CharField( max_length = 200 )
    block_id = models.CharField( max_length = 200 )
    shape_id = models.CharField( max_length = 200 )
    stop_pattern = models.IntegerField()
    
    @property
    def shape_points(self):
        return ShapePoint.objects.all().filter( shape_id=self.shape_id ).order_by('shape_pt_sequence')

    @property
    def shape(self):
        return LineString( [(float(x.shape_pt_lon),float(x.shape_pt_lat)) for x in self.shape_points] )

    @property
    def trip_runs( self ):
        return VehicleUpdate.runs( trip_id=self.trip_id )

    #derived column
    start_time = models.IntegerField(null=True) #the departure time of the first stoptime in this trip

    def str(self):
        return "<Trip %s>"%self.trip_id

class TripSpeedStats( models.Model ):
    trip = models.ForeignKey( Trip )
    stats = models.TextField() #json blob with resolution and string of gamma params

class StopTime( models.Model ):
    class Meta:
        managed = False
        db_table = "stop_times"

    trip = models.ForeignKey( Trip, db_column="trip_id" )
    arrival_time = models.IntegerField()
    departure_time = models.IntegerField()
    stop = models.ForeignKey( Stop, db_column="stop_id" )
    stop_sequence = models.IntegerField()
    stop_headsign = models.CharField( max_length = 200 )
    pickup_type = models.CharField( max_length = 5 )
    drop_off_type = models.CharField( max_length = 200 )
    shape_dist_traveled = models.FloatField()

    percent_along_trip = models.FloatField()

    @property
    def departure_time_str(self):
        hh = self.departure_time/3600
        mm = (self.departure_time%3600)/60
        ss = self.departure_time%60
        return "%02d:%02d:%02d"%(hh,mm,ss)

    def __repr__(self):
        return "<StopTime %s>"%self.departure_time_str

    def __str__(self):
        return repr(self)

class Frequencies( models.Model ):
    class Meta:
        managed = False
        db_table = "frequencies"

    trip = models.ForeignKey( Trip, db_column="trip_id" )
    start_time = models.CharField( max_length=200 )
    end_time = models.CharField( max_length=200 )
    headway_secs = models.IntegerField()
