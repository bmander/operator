from django.http import HttpResponse

def home(req):
    return HttpResponse( "operator. get me out of here." )
