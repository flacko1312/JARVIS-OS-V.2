import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from actions import file_controller


class WindowsKnownFolderPathTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.folders = {
            "desktop": self.root / "Redirected Desktop",
            "documents": self.root / "Mis Documentos",
            "downloads": self.root / "Descargas",
            "pictures": self.root / "Imágenes",
            "music": self.root / "Música",
            "videos": self.root / "Vídeos",
        }
        for folder in self.folders.values():
            folder.mkdir()
        self.known_folder = patch.object(
            file_controller,
            "_known_folder_path",
            side_effect=lambda name: self.folders[name],
        )
        self.safe_roots = patch.object(file_controller, "_SAFE_ROOTS", [])
        self.known_folder.start()
        self.safe_roots.start()

    def tearDown(self):
        self.safe_roots.stop()
        self.known_folder.stop()
        self.temp.cleanup()

    def test_desktop_alias_resolves_child(self):
        self.assertEqual(
            file_controller._resolve_path("desktop/dibujos"),
            self.folders["desktop"] / "dibujos",
        )

    def test_escritorio_alias_resolves_child(self):
        self.assertEqual(
            file_controller._resolve_path("escritorio/dibujos"),
            self.folders["desktop"] / "dibujos",
        )

    def test_documents_and_documentos_aliases(self):
        expected = self.folders["documents"] / "informe.txt"
        self.assertEqual(file_controller._resolve_path("documents/informe.txt"), expected)
        self.assertEqual(file_controller._resolve_path("documentos/informe.txt"), expected)

    def test_downloads_and_descargas_aliases(self):
        expected = self.folders["downloads"] / "archivo.zip"
        self.assertEqual(file_controller._resolve_path("downloads/archivo.zip"), expected)
        self.assertEqual(file_controller._resolve_path("descargas/archivo.zip"), expected)

    def test_spaces_accents_and_all_media_aliases(self):
        self.assertEqual(
            file_controller._resolve_path("escritorio/Proyectos Cloud"),
            self.folders["desktop"] / "Proyectos Cloud",
        )
        self.assertEqual(
            file_controller._resolve_path("imágenes/Dibujos Málaga"),
            self.folders["pictures"] / "Dibujos Málaga",
        )
        self.assertEqual(file_controller._resolve_path("musica/canción.mp3"), self.folders["music"] / "canción.mp3")
        self.assertEqual(file_controller._resolve_path("vídeos/viaje.mp4"), self.folders["videos"] / "viaje.mp4")

    def test_forward_and_back_slashes_are_equivalent(self):
        forward = file_controller._resolve_path("desktop/dibujos/boceto.png")
        backward = file_controller._resolve_path(r"desktop\dibujos\boceto.png")
        self.assertEqual(forward, backward)

    def test_alias_traversal_is_rejected(self):
        for value in ("desktop/../../Windows", r"escritorio\..\..\Windows", r"..\.."):
            with self.subTest(value=value):
                result = file_controller.open_file(value)
                self.assertIn("Access denied", result)

    def test_protected_windows_absolute_path_is_rejected(self):
        result = file_controller.open_file(r"C:\Windows\System32")
        self.assertIn("Access denied", result)

    def test_valid_missing_known_folder_child_is_not_found(self):
        result = file_controller.open_file("desktop/no-existe")
        self.assertIn("Not found", result)
        self.assertNotIn("Access denied", result)

    def test_existing_folder_file_and_shortcut_open(self):
        folder = self.folders["desktop"] / "dibujos"
        folder.mkdir()
        document = self.folders["desktop"] / "boceto.txt"
        document.write_text("test", encoding="utf-8")
        shortcut = self.folders["desktop"] / "aplicación.lnk"
        shortcut.write_bytes(b"test shortcut placeholder")

        with (
            patch.object(file_controller, "_OS", "Windows"),
            patch.object(file_controller.os, "startfile", create=True) as startfile,
        ):
            self.assertEqual(file_controller.open_file("desktop/dibujos"), "Opened folder: dibujos")
            self.assertEqual(file_controller.open_file("desktop/boceto.txt"), "Opened file: boceto.txt")
            self.assertEqual(file_controller.open_file("escritorio/aplicación.lnk"), "Opened file: aplicación.lnk")

        self.assertEqual(startfile.call_count, 3)

    def test_existing_absolute_approved_path_still_opens(self):
        child = self.folders["documents"] / "normal.txt"
        child.write_text("test", encoding="utf-8")
        with (
            patch.object(file_controller, "_OS", "Windows"),
            patch.object(file_controller.os, "startfile", create=True) as startfile,
        ):
            result = file_controller.open_file(str(child))
        self.assertEqual(result, "Opened file: normal.txt")
        startfile.assert_called_once_with(str(child))


class WindowsKnownFolderApiTests(unittest.TestCase):
    def test_each_windows_folder_uses_current_user_known_folder_api(self):
        expected = Path(r"D:\Redirected\Desktop")
        with (
            patch.object(file_controller, "_OS", "Windows"),
            patch.object(file_controller, "_windows_known_folder_path", return_value=expected) as resolver,
        ):
            self.assertEqual(file_controller._get_desktop(), expected)
        resolver.assert_called_once_with("desktop")


if __name__ == "__main__":
    unittest.main()
