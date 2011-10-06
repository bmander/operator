from django.http import HttpResponse

# Create your views here.

def home(req):
   return HttpResponse( "hi" )
