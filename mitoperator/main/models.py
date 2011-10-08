from django.db import models

# Create your models here.

class Info( models.Model ):
    timestamp = models.IntegerField() 

class StopTimeUpdate(models.Model):
    trip_id = models.CharField(max_length=200)
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

