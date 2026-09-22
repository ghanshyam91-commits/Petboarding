from django.contrib import admin
from django.contrib.auth import views as auth
from django.urls import path
from care import views
from config.health import health

urlpatterns = [
    path("healthz/", health, name="health"),
    path("admin/", admin.site.urls),
    path(
        "login/", auth.LoginView.as_view(template_name="care/login.html"), name="login"
    ),
    path("logout/", auth.LogoutView.as_view(), name="logout"),
    path("", views.home, name="home"),
    path("explore/", views.explore, name="explore"),
    path("providers/<int:pk>/reserve/", views.book, name="book"),
    path("bookings/", views.bookings, name="bookings"),
    path("stays/<int:pk>/", views.stay, name="stay"),
    path("stays/<int:pk>/emergency/", views.emergency, name="emergency"),
    path("stays/<int:pk>/cancel/", views.cancellation, name="cancel"),
    path("stays/<int:pk>/message/", views.send_message, name="send_message"),
    path("profile/", views.profile, name="profile"),
    path("messages/", views.inbox, name="inbox"),
    path("operations/", views.operations, name="operations"),
    path("tasks/<int:pk>/complete/", views.task_complete, name="task_complete"),
    path("trust/", views.trust, name="trust"),
    path("trust/providers/<int:pk>/suspend/", views.suspend, name="suspend"),
]
urlpatterns += [
    path("stays/<int:pk>/handover/", views.handover, name="handover"),
    path("stays/<int:pk>/review/", views.review, name="review"),
    path("stays/<int:pk>/dispute/", views.dispute, name="dispute"),
    path("privacy/request/", views.privacy_request, name="privacy_request"),
]
