from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier
from unittest import skipUnless

from django.db import close_old_connections, connection, connections
from django.test import Client, TransactionTestCase

from .models import History, User, Voc, VocType


@skipUnless(connection.vendor == "postgresql", "운영 PostgreSQL 동시 트랜잭션 인수 시험")
class ConcurrentRequests(TransactionTestCase):
    def in_parallel(self, actions):
        ready = Barrier(len(actions))

        def invoke(action):
            close_old_connections()
            try:
                ready.wait(timeout=10)
                return action().status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=len(actions)) as pool:
            return sorted(pool.map(invoke, actions))

    def test_simultaneous_signup(self):
        def register():
            return Client().post("/signup", {"username": "same", "name": "동시 가입",
                                             "department": "개발", "employee_id": "00001"})

        self.assertEqual(self.in_parallel([register, register]), [200, 302])
        self.assertEqual(User.objects.filter(username="same").count(), 1)

    def test_simultaneous_status_change(self):
        actions = []
        users = [User.objects.create(username=name, name=name, role="developer") for name in ("aa", "bb")]
        voc = Voc.objects.create(reporter=users[0], creator=users[0], title="동시 처리", body="상태 변경",
                                 registered=date.today(), kind=VocType.objects.create(name="문의"))
        History.objects.create(voc=voc, after="접수", actor=users[0])
        for developer in users:
            client = Client()
            client.force_login(developer)
            actions.append(lambda c=client: c.post(f"/vocs/{voc.pk}/transition",
                           {"status": "보류", "reason": "처리 확인", "version": str(voc.version)}))

        self.assertEqual(self.in_parallel(actions), [302, 409])
        voc.refresh_from_db()
        self.assertEqual((voc.status, voc.version, voc.history.count()), ("보류", 2, 2))
