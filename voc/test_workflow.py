from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from .models import Attachment, Equipment, History, User, Voc, VocType


class WorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = User.objects.create(username="first", name="등록자", department="사업부")
        cls.reporter = User.objects.create(username="second", name="제기자", department="사업부")
        cls.developer = User.objects.create(username="dev", name="개발 담당", role="developer")
        cls.kind = VocType.objects.create(name="시험 유형")
        cls.tags = [Equipment.objects.create(name=name) for name in ("설비 A", "설비 B")]

    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.media = Path(directory.name)
        self.enterContext(self.settings(MEDIA_ROOT=self.media))
        self.client.force_login(self.author)

    def submit(self, **extra):
        return self.client.post(reverse("new"), {
            "reporter": self.reporter.pk, "kind": self.kind.pk, "registered": "2026-05-06",
            "title": "대리 등록 시험", "body": "상세 내용", "screen": "0007",
            "equipment": [tag.pk for tag in self.tags], **extra,
        })

    def test_proxy_submission_with_files_links_and_protected_preview(self):
        png = BytesIO()
        Image.new("RGB", (4, 4)).save(png, "PNG")
        response = self.submit(
            files=[SimpleUploadedFile("screen.png", png.getvalue()), SimpleUploadedFile("notes.txt", b"test")],
            links="https://example.org/docs\n" + r"\\server\share\notes.txt",
        )
        voc = Voc.objects.get()
        self.assertRedirects(response, reverse("detail", args=[voc.pk]))
        self.assertEqual((voc.reporter, voc.creator, voc.screen), (self.reporter, self.author, "0007"))
        self.assertCountEqual(voc.equipment.all(), self.tags)
        self.assertEqual(voc.history.get().actor, self.author)
        self.assertCountEqual(voc.attachments.values_list("kind", flat=True), ["file", "file", "web", "unc"])
        attachment = voc.attachments.get(name="screen.png")
        url = reverse("attachment", args=[attachment.pk]) + "?preview=1"
        response = self.client.get(url)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(b"".join(response.streaming_content), png.getvalue())
        self.assertEqual(self.client.get(reverse("vocs"), {"mine": "1"}).context["page"].paginator.count, 0)
        self.client.force_login(self.reporter)
        self.assertEqual(self.client.get(reverse("vocs"), {"mine": "1", "q": "0007"}).context["page"].paginator.count, 1)
        User.objects.filter(pk=self.reporter.pk).update(is_active=False)
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_failed_initial_history_rolls_back_record_and_uploaded_file(self):
        with patch.object(History.objects, "create", side_effect=OSError("disk error")):
            response = self.submit(files=[SimpleUploadedFile("notes.txt", b"notes")])
        self.assertTrue(response.context["form"].non_field_errors())
        self.assertFalse(Voc.objects.exists())
        self.assertFalse(Attachment.objects.exists())
        self.assertFalse(any(path.is_file() for path in self.media.rglob("*")))

    def test_state_machine_preserves_first_result_and_all_reasons(self):
        self.submit()
        voc = Voc.objects.get()
        url = reverse("transition", args=[voc.pk])
        hold = {"version": voc.version, "status": "보류", "reason": "  장비 대기  "}
        self.assertEqual(self.client.post(url, hold).status_code, 403)
        self.client.force_login(self.developer)
        for state in ("보류", "수용 불가"):
            self.assertEqual(self.client.post(url, {**hold, "status": state, "reason": "  "}).status_code, 400)
        self.assertEqual(self.client.post(url, hold).status_code, 302)
        conflict = self.client.post(url, {**hold, "status": "완료", "completed": "2026-05-08"})
        self.assertContains(conflict, self.developer.name, status_code=409)
        voc.refresh_from_db()
        self.assertEqual(voc.status, "보류")
        done = {"version": voc.version, "status": "완료", "completed": "2026-05-08"}
        self.assertEqual(self.client.post(url, done).status_code, 302)
        self.assertEqual(voc.history.get(after="보류").reason, "장비 대기")
        self.assertEqual(voc.history.get(after="완료").completed.isoformat(), "2026-05-08")
        voc.refresh_from_db()
        self.assertEqual(self.client.post(url, {**hold, "version": voc.version}).status_code, 400)
        User.objects.filter(pk=self.developer.pk).update(role="reporter")
        self.assertEqual(self.client.post(url, hold).status_code, 403)

    def test_dashboard_drilldowns_match_list_with_same_date_and_equipment_filters(self):
        for status in ("접수", "보류", "완료", "수용 불가", "완료"):
            voc = Voc.objects.create(reporter=self.reporter, creator=self.author, title=status, body="내용",
                                     kind=self.kind, registered="2026-05-06", status=status)
            voc.equipment.set(self.tags)
        excluded = Voc.objects.create(reporter=self.reporter, creator=self.author, title="오래된 건", body="내용",
                                      kind=self.kind, registered="2026-05-01")
        excluded.equipment.set(self.tags)
        response = self.client.get(reverse("dashboard"), {"start": "2026-05-06", "equipment": self.tags[0].pk})
        self.assertEqual(response.context["rate"], "40.0%")
        for card in response.context["cards"]:
            self.assertEqual(card["count"], self.client.get(card["url"]).context["page"].paginator.count)
        for row in response.context["rows"]:
            for segment in row["segments"]:
                self.assertEqual(segment["count"], self.client.get(segment["url"]).context["page"].paginator.count)
        self.assertEqual(self.client.get(reverse("dashboard"), {"end": "2020-01-01"}).context["rate"], "—")

    def test_equipment_chart_counts_common_requests_and_multiple_tags(self):
        common = self.submit(equipment=[])
        self.assertContains(self.client.get(common.url), "공통")
        self.assertNotContains(self.client.get(reverse("new")), "equipmentsearch")
        self.submit()
        self.submit(equipment=[self.tags[0].pk])
        self.submit(registered="2026-05-07")

        dashboard = self.client.get(reverse("dashboard"), {"end": "2026-05-06"})
        rows = dashboard.context["equipment_rows"]
        self.assertEqual(rows[0]["name"], self.tags[0].name)
        self.assertEqual({row["name"]: row["count"] for row in rows},
                         {"공통": 1, self.tags[0].name: 2, self.tags[1].name: 1})
        self.assertEqual(dashboard.context["voc_total"], 3)
        for row in rows:
            self.assertEqual(self.client.get(row["url"]).context["page"].paginator.count, row["count"])
        for equipment, expected in (("common", 1), (self.tags[0].pk, 2)):
            dashboard = self.client.get(reverse("dashboard"), {"end": "2026-05-06", "equipment": equipment})
            self.assertEqual([row["count"] for row in dashboard.context["equipment_rows"]], [expected])
