from django.core.management.base import BaseCommand, CommandError

import gtfs_realtime_pb2 as grt
import datetime
from urllib2 import urlopen
from django.db.transaction import commit_on_success
import time

from mitoperator.main.models import StopTimeUpdate, Info, VehicleUpdate

FEED_URL = "http://developer.mbta.com/lib/gtrtfs/Vehicles.pb"

def poll_mbta_vehicle_positions():
    fetch_timestamp = int(time.time())

    # fetch feed from remote server
    fp = urlopen( FEED_URL )
    gtfsrt_message = fp.read()

    # parse it using protocol buffers
    pp = grt.FeedMessage()
    pp.ParseFromString( gtfsrt_message )

    try:
        info = Info.objects.all()[0]
        if info.buspos_timestamp is not None and pp.header.timestamp <= info.buspos_timestamp:
            self.stdout.write( "nothing to do - already have the latest data\n" )
            return
    except IndexError:
        info = Info(buspos_timestamp = pp.header.timestamp)

    ret = []

    print "new timestamp %s > %s old timestamp"%(pp.header.timestamp, info.timestamp)
    info.buspos_timestamp = pp.header.timestamp
    info.save()

    print pp.header

    for i, entity in enumerate( pp.entity ):
        print ".",

        vprec = VehicleUpdate()
        
        if entity.vehicle.HasField('trip'):
            vprec.trip_id = entity.vehicle.trip.trip_id
            vprec.start_date = entity.vehicle.trip.start_date
            vprec.schedule_relationship = entity.vehicle.trip.schedule_relationship

        if entity.vehicle.HasField('position'):
            vprec.latitude = entity.vehicle.position.latitude
            vprec.longitude = entity.vehicle.position.longitude

        vprec.current_stop_sequence = entity.vehicle.current_stop_sequence
        vprec.data_timestamp = entity.vehicle.timestamp

        vprec.fetch_timestamp = fetch_timestamp
        vprec.save()

    print
    print "%s - %s\n"%(datetime.datetime.fromtimestamp( fetch_timestamp), i)

class Command(BaseCommand):
    args = ''
    help = 'poll the MBTA'

    def handle(self, *args, **options):
        poll_mbta_vehicle_positions()
