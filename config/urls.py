from django.contrib import admin
from django.contrib.auth import views as auth
from django.urls import path
from care import views, account_flows, passport_flows, provider_flows, preview_flows
from config.health import health
from care.demo import demo_login

urlpatterns = [
    path("demo/login/", demo_login, name="demo_login"),
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
    path("stays/<int:pk>/handover/", provider_flows.checkin, name="handover"),
    path("stays/<int:pk>/review/", views.review, name="review"),
    path("stays/<int:pk>/dispute/", views.dispute, name="dispute"),
    path("privacy/request/", views.privacy_request, name="privacy_request"),
]

urlpatterns += [
    path("signup/", account_flows.signup, name="signup"),
    path("account/", account_flows.account, name="account"),
    path("pets/<int:pk>/edit/", passport_flows.pet_edit, name="pet_edit"),
    path("pets/<int:pk>/health/add/", passport_flows.health_submit, name="health_submit"),
    path("health/<int:pk>/document/", passport_flows.health_document, name="health_document"),
    path("trust/health/<int:pk>/", passport_flows.health_review, name="health_review"),
    path("stays/<int:pk>/confirm/", provider_flows.confirm_stay, name="confirm_stay"),
    path("stays/<int:pk>/checkout/", provider_flows.checkout, name="checkout"),
    path("stays/<int:pk>/care/", provider_flows.record_care, name="record_care"),
    path("stays/<int:pk>/tasks/", provider_flows.add_task, name="add_task"),
    path("providers/<int:pk>/preview/", preview_flows.provider_preview, name="provider_preview"),
]
