from django.test import Client, TestCase

from .models import Equipment, User


class AccountTests(TestCase):
    def setUp(self):
        self.master = User.objects.create_user(username="operator", role="master", password="operator-test")
        self.data = {"username": "lee", "name": "이담", "department": "운영팀", "employee_id": "00025"}

    def test_signup_uniqueness_and_password(self):
        self.assertFalse(self.client.get("/signup/check", {"username": "operator"}).json()["available"])
        self.assertRedirects(self.client.post("/signup", self.data), "/login")
        self.client.post("/signup", self.data)
        self.assertEqual(User.objects.filter(username="lee").count(), 1)
        self.assertRedirects(self.client.post("/signup", {**self.data, "username": "kim"}), "/login")
        self.assertRedirects(self.client.post("/login", {"username": "lee", "password": "00025"}), "/vocs")
        self.assertEqual(self.client.get("/members").status_code, 403)

    def test_master_adds_equipment_for_voc_forms(self):
        self.assertRedirects(self.client.get("/equipment"), "/login?next=/equipment")
        self.client.force_login(self.master)
        self.assertContains(self.client.get("/members"), 'href="/equipment"')
        self.assertContains(self.client.post("/equipment", {"name": "  "}), "등록된 설비가 없습니다.")
        self.assertRedirects(self.client.post("/equipment", {"name": " 검사기 "}), "/equipment")
        self.assertContains(self.client.post("/equipment", {"name": "검사기"}), "이미 등록된 설비명입니다.")
        self.assertEqual(Equipment.objects.get().name, "검사기")
        self.client.force_login(User.objects.create_user(**self.data))
        self.assertContains(self.client.get("/equipment"), "로그아웃하고 계정 전환", status_code=403)
        self.assertEqual(self.client.post("/equipment", {"name": "추가"}).status_code, 403)
        for path in ("/vocs/new", "/vocs", "/dashboard"):
            self.assertContains(self.client.get(path), "검사기")

    def test_member_actions_apply_on_active_sessions(self):
        user = User.objects.create_user(**self.data, password="00025")
        self.client.force_login(user)
        operator = Client()
        self.assertRedirects(operator.post("/login", {"username": "operator", "password": "operator-test"}), "/members")
        change = {"member": user.pk, "action": "role", "role": "developer"}
        self.assertRedirects(operator.post("/members", change), "/members")
        self.assertEqual(self.client.get("/vocs").wsgi_request.user.role, "developer")
        operator.post("/members", {**change, "role": "reporter"})
        self.assertEqual(self.client.get("/vocs").wsgi_request.user.role, "reporter")
        delete = {"member": user.pk, "action": "delete", "confirm_name": user.name, "confirm_username": user.username}
        self.assertEqual(operator.post("/members", {**delete, "confirm_name": ""}).status_code, 400)
        self.assertEqual(operator.post("/members", {**change, "member": self.master.pk}).status_code, 404)
        self.assertRedirects(operator.post("/members", delete), "/members")
        self.assertRedirects(self.client.get("/vocs"), "/login?next=/vocs")
        self.assertFalse(self.client.get("/signup/check", {"username": user.username}).json()["available"])
        self.client.post("/signup", self.data)
        self.assertFalse(User.objects.get(pk=user.pk).is_active)
