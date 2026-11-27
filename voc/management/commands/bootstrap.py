import os
from getpass import getpass

from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError
from django.db import transaction

from voc.models import Equipment, User, VocType


class Command(BaseCommand):
    help = "초기 VOC 유형·설비와 운영자가 지정한 마스터 계정을 등록합니다."

    def add_arguments(self, parser):
        parser.add_argument("--master", help="마스터 계정명. 비밀번호를 대화형으로 입력합니다.")

    @transaction.atomic
    def handle(self, *args, **options):
        kinds = os.environ.get("VOC_TYPES", "오류,개선 요청,문의,기타")
        for position, name in enumerate(kinds.split(",")):
            if name.strip():
                VocType.objects.get_or_create(name=name.strip(), defaults={"position": position})
        for name in os.environ.get("VOC_EQUIPMENT", "").split(","):
            if name.strip():
                Equipment.objects.get_or_create(name=name.strip())
        username = options["master"] or os.environ.get("MASTER_USERNAME", "")
        password = getpass("마스터 비밀번호: ") if options["master"] else os.environ.get("MASTER_PASSWORD", "")
        if bool(username) != bool(password):
            raise CommandError("마스터 계정명과 비밀번호를 함께 지정하세요.")
        if username:
            username = User.normalize_username(username.strip())
            try:
                User._meta.get_field("username").clean(username, None)
            except ValidationError as exc:
                raise CommandError("유효한 마스터 계정명을 지정하세요.") from exc
            user, created = User.objects.get_or_create(username=username,
                                                       defaults={"role": "master", "name": "운영자"})
            if user.role != "master":
                raise CommandError("기존 회원과 마스터 계정명이 중복됩니다.")
            if created or options["master"]:
                user.set_password(password)
                user.save(update_fields=["password"])
        self.stdout.write(self.style.SUCCESS("초기 설정을 반영했습니다."))
