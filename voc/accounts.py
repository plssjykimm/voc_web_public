from django import forms
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UsernameField
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .models import Equipment, User


class Signup(forms.Form):
    username = UsernameField(label="계정명", max_length=150, validators=[UnicodeUsernameValidator()])
    name = forms.CharField(label="이름", max_length=100)
    department = forms.CharField(label="소속", max_length=120)
    employee_id = forms.CharField(label="사번", max_length=80)


class EquipmentForm(forms.Form):
    name = forms.CharField(label="설비명", max_length=100)


@require_http_methods(["GET", "POST"])
@login_required
def equipment(request):
    if request.user.role != "master":
        return render(request, "equipment_access.html", status=403)
    form = EquipmentForm(request.POST if request.method == "POST" else None)
    if form.is_valid():
        item, created = Equipment.objects.get_or_create(name=form.cleaned_data["name"])
        if created:
            messages.success(request, f"{item.name} 설비를 추가했습니다.")
            return redirect("equipment")
        form.add_error("name", "이미 등록된 설비명입니다.")
    return render(request, "equipment.html", {"form": form, "items": Equipment.objects.all()})


def home(request):
    if not request.user.is_authenticated:
        return redirect("login")
    return redirect("members" if request.user.role == "master" else "vocs")


@require_http_methods(["GET", "POST"])
def signin(request):
    if request.user.is_authenticated:
        return home(request)
    error = ""
    if request.method == "POST":
        user = authenticate(request, username=User.normalize_username(request.POST.get("username", "").strip()),
                            password=request.POST.get("password", ""))
        if user:
            login(request, user)
            return home(request)
        error = "계정명 또는 비밀번호를 확인해 주세요."
    return render(request, "login.html", {"error": error})


@require_POST
def signout(request):
    logout(request)
    return redirect("login")


@require_GET
def available(request):
    try:
        username = Signup.base_fields["username"].clean(request.GET.get("username"))
    except forms.ValidationError:
        return JsonResponse({"available": False})
    return JsonResponse({"available": not User.objects.filter(username=username).exists()})


@require_http_methods(["GET", "POST"])
def signup(request):
    if request.user.is_authenticated:
        return home(request)
    error = ""
    if request.method == "POST":
        form = Signup(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    User.objects.create_user(password=form.cleaned_data["employee_id"], **form.cleaned_data)
            except IntegrityError:
                error = "이미 사용 중인 계정명입니다."
            else:
                messages.success(request, "가입했습니다. 계정명과 사번으로 로그인해 주세요.")
                return redirect("login")
        else:
            error = " ".join(f"{form.fields[k].label} · {msg}" for k, errors in form.errors.items() for msg in errors)
    return render(request, "signup.html", {"error": error})


@require_http_methods(["GET", "POST"])
@login_required
def members(request):
    if request.user.role != "master":
        raise PermissionDenied
    error = ""
    if request.method == "POST":
        with transaction.atomic():
            member_id = request.POST.get("member", "")
            if not member_id.isascii() or not member_id.isdigit() or len(member_id) > 18:
                raise PermissionDenied
            target = get_object_or_404(User.objects.select_for_update().exclude(role="master"), pk=int(member_id), is_active=True)
            action = request.POST.get("action")
            if action == "role" and request.POST.get("role") in ("reporter", "developer"):
                target.role = request.POST["role"]
                target.save(update_fields=["role"])
                messages.success(request, f"{target.name}님의 역할을 변경했습니다.")
            elif (action == "delete" and request.POST.get("confirm_name") == target.name
                  and request.POST.get("confirm_username") == target.username):
                target.is_active = False
                target.save(update_fields=["is_active"])
                messages.success(request, f"{target.name}님의 계정을 비활성화했습니다.")
            else:
                error = "대상 회원과 요청 내용을 확인해 주세요."
        if not error:
            return redirect("members")
    return render(request, "members.html", {"members": User.objects.order_by("-is_active", "name", "username"), "error": error},
                  status=400 if error else 200)
