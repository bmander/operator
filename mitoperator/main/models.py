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

