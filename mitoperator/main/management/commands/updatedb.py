from django.core.management.base import BaseCommand, CommandError

import gtfs_realtime_pb2 as grt
import datetime
from urllib2 import urlopen
from django.db.transaction import commit_on_success
import time

from mitoperator.main.models import Trip

from sys import stdout
class Command(BaseCommand):
    args = ''
    help = 'perform various caching tasks'

    @commit_on_success
    def set_trip_start( self):
        for i, trip in enumerate( Trip.objects.all().filter(start_time=None) ):
            if i%100==0:
                stdout.write( "." )
                stdout.flush

            trip.start_time = trip.stoptime_set.order_by("departure_time")[0].departure_time
            trip.save()

    def handle(self, *args, **options):
        self.set_trip_start()
