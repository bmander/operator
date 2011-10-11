from django.conf.urls.defaults import patterns, include, url

# Uncomment the next two lines to enable the admin:
# from django.contrib import admin
# admin.autodiscover()

urlpatterns = patterns('',
    # Examples:
    url(r'^$', 'main.views.home', name='home'),
    url(r'^deviationrecords$', 'main.views.deviationrecords', name='deviationrecords'),
    url(r'^gpsdeviations$', 'main.views.gpsdeviations', name='gpsdeviations'),
    url(r'^stops$', 'main.views.stops', name='stops'),
    url(r'^stop/(.*)$', 'main.views.stop', name='stop'),
    url(r'^trip/(.*)$', 'main.views.trip', name='trip'),
    url(r'^recent/$', 'main.views.recent', name='recent'),
    url(r'^viz/$', 'main.views.viz', name='viz'),
    url(r'^routes/$', 'main.views.routes', name='routes'),
    url(r'^route/(.*)$', 'main.views.route', name='route'),
    url(r'^positions/$', 'main.views.positions', name='positions'),

    # url(r'^$', 'mitoperator.views.home', name='home'),
    # url(r'^mitoperator/', include('mitoperator.foo.urls')),

    # Uncomment the admin/doc line below to enable admin documentation:
    # url(r'^admin/doc/', include('django.contrib.admindocs.urls')),

    # Uncomment the next line to enable the admin:
    # url(r'^admin/', include(admin.site.urls)),
)
