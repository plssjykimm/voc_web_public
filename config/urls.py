from django.urls import path

from voc import accounts, workflow

urlpatterns = [
    path("", accounts.home, name="home"),
    path("login", accounts.signin, name="login"),
    path("logout", accounts.signout, name="logout"),
    path("signup", accounts.signup, name="signup"),
    path("signup/check", accounts.available, name="available"),
    path("members", accounts.members, name="members"),
    path("equipment", accounts.equipment, name="equipment"),
    path("vocs", workflow.vocs, name="vocs"),
    path("vocs/new", workflow.new, name="new"),
    path("vocs/<int:pk>", workflow.detail, name="detail"),
    path("vocs/<int:pk>/transition", workflow.transition, name="transition"),
    path("attachments/<int:pk>", workflow.attachment, name="attachment"),
    path("dashboard", workflow.dashboard, name="dashboard"),
]
