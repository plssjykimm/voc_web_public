from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    name = models.CharField(max_length=100)
    department = models.CharField(max_length=120)
    employee_id = models.CharField(max_length=80)
    role = models.CharField(max_length=12, default="reporter",
                            choices=[("reporter", "제기자"), ("developer", "개발자"), ("master", "마스터")])

    class Meta:
        db_table = "users"


class VocType(models.Model):
    name = models.CharField(max_length=80, unique=True)
    position = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "voc_types"
        ordering = ["position", "id"]

    def __str__(self):
        return self.name


class Equipment(models.Model):
    name = models.CharField(max_length=100, unique=True)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "equipment"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Voc(models.Model):
    reporter = models.ForeignKey(User, on_delete=models.PROTECT, related_name="reported")
    creator = models.ForeignKey(User, on_delete=models.PROTECT, related_name="submitted")
    title = models.CharField(max_length=240)
    body = models.TextField()
    kind = models.ForeignKey(VocType, on_delete=models.PROTECT)
    screen = models.CharField(max_length=80, blank=True)
    registered = models.DateField(db_index=True)
    created = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=12, default="접수", db_index=True)
    version = models.PositiveIntegerField(default=1)
    equipment = models.ManyToManyField(Equipment, blank=True, db_table="voc_equipment")

    class Meta:
        db_table = "vocs"


class Attachment(models.Model):
    voc = models.ForeignKey(Voc, on_delete=models.CASCADE, related_name="attachments")
    kind = models.CharField(max_length=16)
    name = models.CharField(max_length=255)
    file = models.FileField(upload_to="files/%Y/%m", blank=True)
    size = models.PositiveBigIntegerField(default=0)
    mime = models.CharField(max_length=120, blank=True)
    address = models.TextField(blank=True)

    class Meta:
        db_table = "voc_attachments"


class History(models.Model):
    voc = models.ForeignKey(Voc, on_delete=models.CASCADE, related_name="history")
    before = models.CharField(max_length=12, blank=True)
    after = models.CharField(max_length=12)
    reason = models.TextField(blank=True)
    actor = models.ForeignKey(User, on_delete=models.PROTECT)
    created = models.DateTimeField(auto_now_add=True)
    completed = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "voc_status_history"
