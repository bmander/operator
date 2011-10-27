from django.db import models
from datetime import datetime

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
    def trip_instances(cls, trip_id):
        trip_vehicle_updates = cls.objects.all().filter(trip__pk=trip_id).order_by('data_timestamp')

        ret = {}
        for vehicle_update in trip_vehicle_updates:
            if vehicle_update.start_date not in ret:
                ret[vehicle_update.start_date] = []

            ret[vehicle_update.start_date].append( vehicle_update )

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
    
    @property
    def shape_points(self):
        return ShapePoint.objects.all().filter( shape_id=self.shape_id ).order_by('shape_pt_sequence')

    @property
    def shape(self):
        return LineString( [(float(x.shape_pt_lon),float(x.shape_pt_lat)) for x in self.shape_points] )

    #derived column
    start_time = models.IntegerField(null=True) #the departure time of the first stoptime in this trip

    def str(self):
        return "<Trip %s>"%self.trip_id

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
