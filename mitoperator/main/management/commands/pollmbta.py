from django.core.management.base import BaseCommand, CommandError

import gtfs_realtime_pb2 as grt
import datetime
from urllib2 import urlopen
from django.db.transaction import commit_on_success
import time

from mitoperator.main.models import StopTimeUpdate, Info

FEED_URL = "http://developer.mbta.com/lib/gtrtfs/Passages.pb"

class Command(BaseCommand):
    args = ''
    help = 'poll the MBTA'

    def handle(self, *args, **options):

        fetch_timestamp = int(time.time())

        # fetch feed from remote server
        fp = urlopen( FEED_URL )
        gtfsrt_message = fp.read()

        # parse it using protocol buffers
        pp = grt.FeedMessage()
        pp.ParseFromString( gtfsrt_message )

        try:
            info = Info.objects.all()[0]
            if pp.header.timestamp <= info.timestamp:
                self.stdout.write( "nothing to do - already have the latest data\n" )
                return
        except IndexError:
            info = Info(timestamp = pp.header.timestamp)

        ret = []

        ret.append( "new timestamp %s > %s old timestamp"%(pp.header.timestamp, info.timestamp) )
        info.timestamp = pp.header.timestamp
        info.save()

        # render it into an html response
        ret.append( "%s"%pp.header )

        for i, entity in enumerate( pp.entity ):
            for stu in entity.trip_update.stop_time_update:
                sturec = StopTimeUpdate()
                sturec.trip_id = entity.trip_update.trip.trip_id
                sturec.start_date = entity.trip_update.trip.start_date

                sturec.stop_sequence = stu.stop_sequence
                if stu.HasField( 'stop_id' ): sturec.stop_id = stu.stop_id
                if stu.HasField( 'arrival' ):
                    if stu.arrival.HasField( 'delay' ): sturec.arrival_delay = stu.arrival.delay
                    if stu.arrival.HasField( 'time' ): sturec.arrival_time = stu.arrival.time
                    if stu.arrival.HasField( 'uncertainty' ): sturec.arrival_uncertainty = stu.arrival.uncertainty
                if stu.HasField( 'departure' ):
                    if stu.departure.HasField( 'delay' ): sturec.departure_delay = stu.departure.delay
                    if stu.departure.HasField( 'time' ): sturec.departure_time = stu.departure.time
                    if stu.departure.HasField( 'uncertainty' ): sturec.departure_uncertainty = stu.departure.uncertainty
                sturec.schedule_relationship = stu.schedule_relationship
                sturec.data_timestamp = pp.header.timestamp
                sturec.fetch_timestamp = fetch_timestamp
                sturec.save()
                ret.append( " - create stu: %s - %s"%(entity.trip_update.trip.trip_id, stu) )

        self.stdout.write( "\n".join(ret) )
