"""Exercise the restored Django application in an isolated verification container."""
import os
import sys

import django

django.setup()

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from voc.models import User, Voc, VocType


run_id = os.environ["VERIFY_ID"]
client = Client(HTTP_HOST="localhost")
master_login = client.post("/login", {
    "username": os.environ["VERIFY_MASTER"],
    "password": sys.stdin.readline().rstrip("\r\n"),
}, secure=True)
assert master_login.status_code == 302 and master_login.url == "/members", "Master login failed"
assert client.get("/members", secure=True).status_code == 200, "Member administration failed"
client.post("/logout", secure=True)

payload = (run_id + "\n").encode() + bytes(range(256))
if os.environ["VERIFY_PHASE"] == "seed":
    signup = client.post("/signup", {
        "username": run_id, "name": "복원 검증", "department": "검증", "employee_id": run_id,
    }, secure=True)
    assert signup.status_code == 302 and signup.url == "/login", "Reporter signup failed"
login = client.post("/login", {"username": run_id, "password": run_id}, secure=True)
assert login.status_code == 302 and login.url == "/vocs", "Reporter login failed"
reporter = User.objects.get(username=run_id)
if os.environ["VERIFY_PHASE"] == "seed":
    kind = VocType.objects.filter(active=True).first()
    assert kind is not None, "Backup has no active VOC type"
    created = client.post("/vocs/new", {
        "reporter": reporter.pk, "kind": kind.pk, "registered": timezone.localdate().isoformat(),
        "title": run_id, "body": "복원 검증을 위한 임시 데이터", "screen": "0003",
        "files": SimpleUploadedFile("restore-test.bin", payload),
    }, secure=True)
    assert created.status_code == 302, "VOC creation failed"
voc = Voc.objects.get(creator=reporter, title=run_id, screen="0003")
assert voc.history.get().actor == reporter, "Initial history does not match"
detail = client.get(reverse("detail", args=[voc.pk]), secure=True)
assert detail.status_code == 200 and run_id.encode() in detail.content, "VOC detail failed"
file = voc.attachments.get(name="restore-test.bin")
download = client.get(reverse("attachment", args=[file.pk]), secure=True)
try:
    assert download.status_code == 200 and b"".join(download.streaming_content) == payload
finally:
    download.close()
print(f"{os.environ['VERIFY_PHASE']}: login, VOC {voc.pk}, history, {len(payload)} attachment bytes verified")
