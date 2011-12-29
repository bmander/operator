import sys

sys.path.append('/home/brandon/operator/mitoperator')

from main.models import Stop
import time

def web_socket_do_extra_handshake(request):
    pass

def web_socket_transfer_data(request):
    #message = request.ws_stream.receive_message()
    #request.ws_stream.send_message(message+" baller")

    #for stop in Stop.objects.all():
    #    request.ws_stream.end_message( stop.stop_name )
    #    time.sleep(0.2)
    
    for stop in Stop.objects.all():
        request.ws_stream.send_message(str(stop.stop_name))
        time.sleep(0.2)

def web_socket_passive_closing_handshake(request):
    pass


if __name__=='__main__':
    for stop in Stop.objects.all():
        print stop.stop_name
        time.sleep(0.2)
