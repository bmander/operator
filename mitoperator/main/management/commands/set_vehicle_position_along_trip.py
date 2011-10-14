from django.core.management.base import BaseCommand, CommandError

import gtfs_realtime_pb2 as grt
import datetime
from urllib2 import urlopen
from django.db.transaction import commit_on_success
import time

from mitoperator.main.models import Trip, StopTime, ShapePoint, Stop

from sys import stdout
from shapely.geometry import LineString, Point

from django.db import transaction
from django.db.models import F

class Command(BaseCommand):
    args = ''
    help = 'perform various caching tasks'

    """
    @transaction.commit_manually
    def handle(self, *args, **options):
        print "collecting shape linestrings"
        shape_ids = ShapePoint.objects.all().values('shape_id').distinct()
        shapes = {}
        for i, rec in enumerate( shape_ids ):
            if i%20==0:
                print i

            shape_id = rec['shape_id']
            shapes[shape_id] = ShapePoint.shape( shape_id )

        print "collecting stop points"
        stop_points = {}
        for i, stop in enumerate( Stop.objects.all() ):
            if i%200==0:
                print i

            stop_points[stop.stop_id]=Point(stop.stop_lat, stop.stop_lon)

        print "collecting trip linestrings"
        trip_linestrings = {}
        for i, trip in enumerate( Trip.objects.all() ):
            if i%200==0:
                print i

            trip_linestrings[trip.trip_id] = shapes.get( trip.shape_id )
        
        n = 0
        while True:
            stoptimes = StopTime.objects.all() \
                        .filter(percent_along_trip__isnull=True, trip__shape_id__isnull=False) \
                        .order_by('trip')[:10000]

            if len(stoptimes)==0:
                break

            for i, stoptime in enumerate( stoptimes ):
                n += 1
                if n%100==0:
                    print n

                linestring = trip_linestrings.get( stoptime.trip_id )
                point = stop_points.get( stoptime.stop_id )

                if linestring is not None and point is not None:
                    stoptime.percent_along_trip = linestring.project( point, normalized=True )
                    stoptime.save()

            transaction.commit()
    """

    def handle(self, *args, **options):
        trip_ids = args

        shapes = {}
        trips = {}

        for trip in Trip.objects.all().filter( trip_id__in = trip_ids ):
            trips[trip.trip_id] = trip

            if trip.shape_id not in shapes:
                shapes[trip.shape_id] = trip.shape
            shape = shapes[trip.shape_id]

            for vehicleupdate in trip.vehicleupdate_set.all().filter(percent_along_trip__isnull=True):
                vehicleupdate.percent_along_trip = shape.project( vehicleupdate.shape, normalized=True )
                vehicleupdate.save()
