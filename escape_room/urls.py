"""
URL configuration for escape_room project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from game.views import ping_player, player_state, role_page, room, room_detail, room_status, win_page

urlpatterns = [
    path('', room, name='home'),
    path('room/<str:code>/', room_detail, name='room'),
    path('room/<str:code>/status/', room_status, name='room_status'),
    path('room/<str:code>/ping/', ping_player, name='ping_player'),
    path('room/<str:code>/state/', player_state, name='player_state'),
    path('room/<str:code>/play/', role_page, name='role_page'),
    path('room/<str:code>/win/', win_page, name='win_page'),
    path('admin/', admin.site.urls),
]
