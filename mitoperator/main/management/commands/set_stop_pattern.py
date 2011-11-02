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

import sys

class Command(BaseCommand):
    args = ''
    help = ''

    #@transaction.commit_manually
    def handle(self, *args, **options):

        trip_patterns = {}

        dateordinal = date.today().toordinal()
        filters = {}
        #filters = {'service_period__start_date__lte':dateordinal,
        #           'service_period__end_date__gte':dateordinal}

        # optional route id
        if len(args) > 0:
            route_id = args[0]
            filters = {'route__route_id':route_id}

        n = Trip.objects.all().count()

        for i, trip in enumerate( Trip.objects.all().filter( **filters ) ):
            sys.stdout.write( "%f\r"%(100*i/float(n)) )
            sys.stdout.flush()

            stoptimes = trip.stoptime_set.all().filter( )
            trip_pattern = tuple([stoptime.stop_id for stoptime in stoptimes])

            if trip_pattern not in trip_patterns:
                pattern_id = len(trip_patterns)
                trip_patterns[trip_pattern] = pattern_id
            else:
                pattern_id = trip_patterns[trip_pattern]

            trip.stop_pattern = pattern_id
            trip.save()

        print len(trip_patterns)
