from __future__ import annotations

import io
import tarfile
import tempfile
import unittest
from pathlib import Path

import numpy as np

from bench.audio_io import read_wav, write_wav
from bench.download_models import file_receipts, install_direct_model, safe_extract


class AudioTest(unittest.TestCase):
    def test_wav_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.wav"
            original = np.array([-32768, -1, 0, 1, 32767], dtype=np.int16)
            write_wav(path, original)
            samples, sample_rate = read_wav(path)
            self.assertEqual(sample_rate, 16000)
            np.testing.assert_array_equal(
                np.rint(samples * 32768).astype(np.int16), original
            )


class ExtractionTest(unittest.TestCase):
    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "bad.tar"
            with tarfile.open(archive, "w") as tar:
                info = tarfile.TarInfo("../outside.txt")
                payload = b"bad"
                info.size = len(payload)
                tar.addfile(info, io.BytesIO(payload))
            with self.assertRaises(ValueError):
                safe_extract(archive, root / "extract")

    def test_extracts_regular_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "good.tar"
            with tarfile.open(archive, "w") as tar:
                info = tarfile.TarInfo("model/tokens.txt")
                payload = b"token 1\n"
                info.size = len(payload)
                tar.addfile(info, io.BytesIO(payload))
            destination = root / "extract"
            safe_extract(archive, destination)
            self.assertEqual((destination / "model" / "tokens.txt").read_bytes(), payload)


class ReceiptTest(unittest.TestCase):
    def test_file_receipts_include_size_and_hash(self):
        with tempfile.TemporaryDirectory(dir="bench") as tmp:
            path = Path(tmp) / "model.bin"
            path.write_bytes(b"model")
            relative = path.resolve().relative_to(Path.cwd().resolve())
            receipts = file_receipts({"required": ["model"], "model": str(relative)})
            self.assertEqual(receipts[0]["bytes"], 5)
            self.assertEqual(len(receipts[0]["sha256"]), 64)

    def test_cached_file_preserves_previous_source(self):
        with tempfile.TemporaryDirectory(dir="bench") as tmp:
            directory = Path(tmp)
            path = directory / "model.bin"
            path.write_bytes(b"model")
            relative_dir = str(directory.resolve().relative_to(Path.cwd().resolve()))
            relative_path = str(path.resolve().relative_to(Path.cwd().resolve()))
            mirror_url = "https://mirror.invalid/model.bin"
            spec = {
                "source_page": "https://source.invalid",
                "download_base": "https://origin.invalid",
                "download_mirror_base": "https://mirror.invalid",
                "download_dir": relative_dir,
                "download_files": ["model.bin"],
                "required": ["model"],
                "model": relative_path,
            }
            previous = {
                "sources": [{"path": relative_path, "url": mirror_url}]
            }
            receipt = install_direct_model("test", spec, True, previous)
            self.assertEqual(receipt["sources"][0]["url"], mirror_url)
            self.assertEqual(receipt["sources"][0]["status"], "cached")


if __name__ == "__main__":
    unittest.main()
