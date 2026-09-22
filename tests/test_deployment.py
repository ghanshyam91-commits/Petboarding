from unittest.mock import patch

from django.db import OperationalError
from django.test import TestCase, override_settings


@override_settings(SECURE_SSL_REDIRECT=True, SECURE_REDIRECT_EXEMPT=[r"^healthz/$"])
class DeploymentHealthTests(TestCase):
    def test_health_checks_database_without_login_or_redirect(self):
        response = self.client.get("/healthz/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_database_failure_is_unhealthy_and_does_not_leak_details(self):
        with patch("config.health.connection.cursor", side_effect=OperationalError("secret")):
            response = self.client.get("/healthz/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "unavailable"})

    def test_normal_pages_still_redirect_to_https(self):
        self.assertEqual(self.client.get("/login/").status_code, 301)
