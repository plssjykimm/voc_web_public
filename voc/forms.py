import re
import warnings
from urllib.parse import urlsplit

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.utils import timezone
from PIL import Image

from .models import Equipment, User, VocType


class MultipleFiles(forms.ClearableFileInput):
    allow_multiple_selected = True


class UploadsField(forms.FileField):
    widget = MultipleFiles

    def clean(self, data, initial=None):
        if not data:
            return []
        items = data if isinstance(data, (tuple, list)) else [data]
        limit = getattr(settings, "VOC_MAX_FILE_SIZE", 20 * 1024 * 1024)
        files = []
        for item in items:
            upload = super().clean(item, initial)
            if upload.size > limit:
                raise ValidationError(f"{upload.name}: 파일 크기 한도({limit:,}바이트)를 초과했습니다.")
            files.append(upload)
        return files


class ReporterChoice(forms.ModelChoiceField):
    def label_from_instance(self, user):
        return f"{user.name} · {user.department} ({user.username})"


class VocForm(forms.Form):
    reporter = ReporterChoice(label="제기자", queryset=User.objects.none(), empty_label=None)
    registered = forms.DateField(label="등록일", initial=timezone.localdate,
                                 widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}))
    kind = forms.ModelChoiceField(label="유형", queryset=VocType.objects.none(), empty_label="유형 선택")
    title = forms.CharField(label="제목", max_length=240)
    body = forms.CharField(label="상세 내용", widget=forms.Textarea(attrs={"rows": 7}))
    equipment = forms.ModelMultipleChoiceField(label="관련 설비", queryset=Equipment.objects.none(),
                                               required=False, widget=forms.CheckboxSelectMultiple)
    screen = forms.CharField(label="화면번호", max_length=80, required=False)
    files = UploadsField(label="첨부파일", required=False)
    links = forms.CharField(label="드라이브 링크 또는 공유 경로", required=False,
                            widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["reporter"].queryset = User.objects.filter(
            is_active=True, role__in=("reporter", "developer")
        ).order_by("name", "department", "username")
        self.fields["reporter"].initial = user.pk
        self.fields["kind"].queryset = VocType.objects.filter(active=True).order_by("position", "pk")
        self.fields["equipment"].queryset = Equipment.objects.filter(active=True).order_by("name")

    def clean_links(self):
        links = []
        validate = URLValidator(schemes=("http", "https"))
        for line in self.cleaned_data["links"].splitlines():
            address = line.strip()
            if not address:
                continue
            if len(address) > 2048 or any(ord(c) < 32 for c in address):
                raise ValidationError("주소 형식 또는 길이를 확인해 주세요.")
            if address.startswith("\\\\"):
                parts = address[2:].split("\\")
                if len(parts) < 2 or not all(parts[:2]) or parts[0] in ("?", "."):
                    raise ValidationError("공유 경로에 서버명과 공유 폴더명을 입력해 주세요.")
                links.append(("unc", address))
            else:
                try:
                    parts = urlsplit(address)
                    if parts.scheme not in ("http", "https") or not parts.hostname or "\\" in address:
                        raise ValueError()
                    # Validate single-label intranet names using the same URL rules as a DNS name.
                    if re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", parts.hostname):
                        port = f":{parts.port}" if parts.port is not None else ""
                        credentials, separator, _ = parts.netloc.rpartition("@")
                        qualified = f"{credentials}{separator}{parts.hostname}.internal{port}"
                        validate(parts._replace(netloc=qualified).geturl())
                    else:
                        validate(address)
                except (ValidationError, ValueError):
                    raise ValidationError("웹 링크는 http 또는 https 주소로 입력해 주세요.")
                links.append(("web", address))
        return links


def upload_mime(upload):
    """Only verified raster images can be rendered inline by the download view."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            picture = Image.open(upload)
            mime = {"PNG": "image/png", "JPEG": "image/jpeg", "GIF": "image/gif",
                    "WEBP": "image/webp"}.get(picture.format)
            if mime:
                picture.verify()
                return mime
    except (ValueError, OSError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        pass
    finally:
        upload.seek(0)
    return "application/octet-stream"
