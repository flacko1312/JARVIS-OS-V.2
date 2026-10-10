import asyncio
import unittest

from api.lilith_notifications import deliver_lilith_voice_notification, notification_voice_prompt


class LilithNotificationVoiceTests(unittest.TestCase):
    def test_voice_prompt_uses_live_engine_text(self):
        sent = []

        class FakeEngine:
            async def send_text(self, text):
                sent.append(text)
                return True

        item = {
            "notification_id": "notif_1",
            "severity": "critical",
            "title": "Backup fallido",
            "summary": "Revisar copia nocturna.",
            "voice_eligible": True,
        }

        delivered = asyncio.run(deliver_lilith_voice_notification(FakeEngine(), item))

        self.assertTrue(delivered)
        self.assertEqual(len(sent), 1)
        self.assertIn("[NOTIFICACION PROACTIVA DE LILITH]", sent[0])
        self.assertIn("Backup fallido", sent[0])
        self.assertNotIn("lilith/accion/speak", sent[0])

    def test_voice_delivery_ignores_non_voice_eligible_items(self):
        class FakeEngine:
            async def send_text(self, _text):
                raise AssertionError("send_text should not be called")

        item = {"notification_id": "notif_1", "title": "Info", "voice_eligible": False}

        delivered = asyncio.run(deliver_lilith_voice_notification(FakeEngine(), item))

        self.assertFalse(delivered)

    def test_prompt_never_allows_actions(self):
        prompt = notification_voice_prompt({
            "severity": "warning",
            "title": "Servicio detenido",
            "summary": "Solo informa al usuario.",
        })

        self.assertIn("sin ejecutar herramientas", prompt)
        self.assertIn("ni iniciar acciones", prompt)


if __name__ == "__main__":
    unittest.main()
