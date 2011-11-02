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

from datetime import date
from optparse import make_option

def get_progresses(linestring, stoptimes):
    # given a linestring and a bunch of stops, finds the projection of each stop along the linestring

    for stoptime in stoptimes:

        point = stoptime.stop.shape

        if point is None:
            yield None
        else:
            yield linestring.project( point, normalized=True ) 

class Command(BaseCommand):
    args = ''
    help = 'perform various caching tasks'

    option_list = BaseCommand.option_list + (
        make_option( '--rework',
                     action='store_true',
                     dest='rework',
                     default=False,
                     help="determine percent_along_trip even if already determined" ),
    )

    #@transaction.commit_manually
    def handle(self, *args, **options):
        shape_cache = {}
        trip_pattern_cache = {}

        dateordinal = date.today().toordinal()
        filters = {'service_period__start_date__lte':dateordinal,
                   'service_period__end_date__gte':dateordinal,
                   'shape_id__isnull':False}

        # optional route id
        if len(args) > 0:
            route_id = args[0]
            filters = {'route__route_id':route_id}

        n = 0
        for trip in Trip.objects.all().filter( **filters ):
            print trip.trip_id,

            stoptimes = trip.stoptime_set.all().select_related('stop').filter( percent_along_trip__isnull = not options['rework'] )
            trip_pattern = (trip.trip_id, tuple([stoptime.stop_id for stoptime in stoptimes]))

            print len(stoptimes)

            if trip.shape_id not in shape_cache:
                linestring = trip.shape
                shape_cache[trip.shape_id] = linestring
                print "%d shapes"%len(shape_cache)
            else:
                linestring = shape_cache[trip.shape_id]

            if linestring is None:
                continue

            if trip_pattern not in trip_pattern_cache:
                progresses = list( get_progresses( linestring, stoptimes ) )
                trip_pattern_cache[trip_pattern] = progresses
            else:
                progresses = trip_pattern_cache[trip_pattern]

            for stoptime, progress in zip( stoptimes, progresses ):
                stoptime.percent_along_trip = progress
                stoptime.save()

            #transaction.commit()
