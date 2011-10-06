from django.http import HttpResponse

from models import StopTimeUpdate
from django.db.models import Count

def home(req):
    n = StopTimeUpdate.objects.all().count()
    n_trips = StopTimeUpdate.objects.values('trip_id').annotate(Count('trip_id')).count()

    return HttpResponse( """<html><body><p>%d data points</br>
%s trips</p>
<p>operator. get me out of here.</p></body></html>"""%(n,n_trips) )

def deviation(request):
    trip_id = request.GET['trip_id']

    stu = StopTimeUpdate.objects.all().filter(trip_id=trip_id).order_by("-fetch_timestamp")[0]

    return HttpResponse( str(stu.arrival_delay) )
