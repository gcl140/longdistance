from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include, re_path
from catalog.media_serve import serve_media
from django.views.generic import RedirectView
from django.views.static import serve
from django.conf.urls import handler404
from django.urls import path
from django.contrib.auth import logout
from django.shortcuts import redirect


handler404 = 'yuzzaz.views.custom_404_view'

def logout_then_google(request):
    logout(request)
    return redirect('/oauth/login/google-oauth2/?next=/profile/')



urlpatterns = [
    path('admin/', admin.site.urls),
    path('home/', include('yuzzaz.urls')),
    path('parties/', include('parties.urls')),
    path('friends/', include('friends.urls')),
    path('notifications/', include('notifications.urls')),
    path('catalog/', include('catalog.urls')),
    path('calendar/', include('schedule.urls')),
    path('oauth/', include('social_django.urls', namespace='social')),
    path('oauth/login/google/', logout_then_google, name='logout-then-google'),
    path('accounts/login/', RedirectView.as_view(url='/login/', permanent=True)),
]




# Media is always served by our range-aware view so the video player can seek.
urlpatterns += [re_path(r'^media/(?P<path>.*)$', serve_media)]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
else:
    urlpatterns += [
        path('static/<path:path>/', serve, {'document_root': settings.STATIC_ROOT}),
    ]
