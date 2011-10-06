from gtfs import Schedule
from datetime import date

def trips_on_date( sched, querydate, querystop ):
    #find gregorian ordinal of query date
    dateord = querydate.toordinal()

    #get a set of service_ids that run on this date on this day of week
    dow = querydate.weekday()
    dow_column = {0:'monday',1:'tuesday',2:'wednesday',3:'thursday',4:'friday',5:'saturday',6:'sunday'}
    query = """SELECT service_id FROM calendar WHERE start_date <= %d AND end_date >= %d AND %s='1'"""%(dateord, dateord, dow_column[dow])
    service = set([x[0] for x in sched.session.execute( query )])

    # get exceptions on that date
    query = """SELECT service_id, exception_type FROM calendar_dates WHERE date=%s"""%dateord
    for service_id, exception_type in list( sched.session.execute( query ) ):
        if exception_type==u'1':
            service.add( service_id )
        elif exception_type==u'2':
            service.remove( service_id )

    # build query
    service_str = ",".join(["'%s'"%ss for ss in service])
    query = """
    SELECT routes.route_id, routes.route_short_name, routes.route_long_name, 
    stop_times.*, 
    trips.service_id 
    FROM stop_times, trips, routes
    WHERE stop_id='%s' 
      AND stop_times.trip_id=trips.trip_id
      AND routes.route_id = trips.route_id
      AND trips.service_id IN (%s)
    ORDER BY stop_times.departure_time"""%(querystop,service_str)

    # execute and return query
    for route_id, route_short_name, route_long_name, trip_id, arrival_time, departure_time, stop_id, stop_sequence, stop_headsign, pickup_type, drop_off_type, shape_dist_traveled, id, service_id in list( sched.session.execute( query ) ):
        yield route_id, route_short_name, route_long_name, arrival_time, departure_time, trip_id

if __name__=='__main__':
    sched = Schedule( 'massachusetts-archiver_20110913_0233.db' )
    querydate = date.today()
    #querydate = date(2011,12,25)
    querystop = 9256

    for rec in trips_on_date( sched, querydate, querystop ):
        print rec

