#!/usr/bin/env python3

"""Video and device-recording tests (no Pillow needed): python3 -m unittest test_fast_media"""

from __future__ import annotations

import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fast_device  # noqa: E402
import fast_media  # noqa: E402
import fast_ui_report  # noqa: E402

# Writes <out> as an H.264 clip of <width>x<height> at a high bitrate, <frames> frames at 24 fps.
MAKE_CLIP = '''
import AVFoundation
let args = CommandLine.arguments
let out = URL(fileURLWithPath: args[1])
let width = Int(args[2])!, height = Int(args[3])!, frames = Int(args[4])!
try? FileManager.default.removeItem(at: out)
let writer = try! AVAssetWriter(outputURL: out, fileType: .mp4)
let input = AVAssetWriterInput(mediaType: .video, outputSettings: [
    AVVideoCodecKey: AVVideoCodecType.h264, AVVideoWidthKey: width, AVVideoHeightKey: height,
    AVVideoCompressionPropertiesKey: [AVVideoAverageBitRateKey: 20_000_000],
])
let adaptor = AVAssetWriterInputPixelBufferAdaptor(assetWriterInput: input, sourcePixelBufferAttributes: [
    kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA,
    kCVPixelBufferWidthKey as String: width, kCVPixelBufferHeightKey as String: height,
])
writer.add(input)
writer.startWriting()
writer.startSession(atSourceTime: .zero)
for index in 0..<frames {
    var buffer: CVPixelBuffer?
    CVPixelBufferPoolCreatePixelBuffer(nil, adaptor.pixelBufferPool!, &buffer)
    CVPixelBufferLockBaseAddress(buffer!, [])
    let base = CVPixelBufferGetBaseAddress(buffer!)!.assumingMemoryBound(to: UInt8.self)
    let row = CVPixelBufferGetBytesPerRow(buffer!)
    for y in 0..<height { for x in 0..<width {
        let pixel = base + y * row + x * 4
        pixel[0] = UInt8((x * 7 + index * 13) & 255); pixel[1] = UInt8((y * 3 + index * 5) & 255)
        pixel[2] = UInt8(((x ^ y) + index) & 255); pixel[3] = 255
    } }
    CVPixelBufferUnlockBaseAddress(buffer!, [])
    while !input.isReadyForMoreMediaData { usleep(1000) }
    adaptor.append(buffer!, withPresentationTime: CMTime(value: CMTimeValue(index), timescale: 24))
}
input.markAsFinished()
let done = DispatchSemaphore(value: 0)
writer.finishWriting { done.signal() }
done.wait()
print(writer.status == .completed ? "ok" : "failed")
'''

# Prints "<width>x<height> <codec>" of a clip's video track.
CLIP_INFO = '''
import AVFoundation
let track = AVURLAsset(url: URL(fileURLWithPath: CommandLine.arguments[1])).tracks(withMediaType: .video)[0]
let codec = CMFormatDescriptionGetMediaSubType(track.formatDescriptions[0] as! CMFormatDescription)
let name = String(bytes: [24, 16, 8, 0].map { UInt8((codec >> $0) & 255) }, encoding: .ascii)!
print("\\(Int(track.naturalSize.width))x\\(Int(track.naturalSize.height)) \\(name)")
'''


def fake_encoder(size: int, returncode: int = 0):
    """A stand-in for the shrink helper that writes `size` bytes to its output argument."""
    def run(args, **kwargs):
        if returncode == 0:
            Path(args[-3]).write_bytes(b"e" * size)
        return mock.Mock(returncode=returncode, stdout="", stderr="")
    return run


class ShrinkVideoTests(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch.object(fast_media, "helper_command", return_value=["shrink"])
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_smaller_encode_replaces_the_original_under_the_target_name(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            source = Path(raw) / "Screen Recording.mp4"
            source.write_bytes(b"r" * 1000)
            with mock.patch.object(fast_media.subprocess, "run", side_effect=fake_encoder(100)):
                kept = fast_media.shrink_video(source, Path(raw) / "run.mp4")
            self.assertEqual(kept, Path(raw) / "run.mp4")
            self.assertEqual(kept.read_bytes(), b"e" * 100)
            self.assertFalse(source.exists())
            self.assertEqual(sorted(p.name for p in Path(raw).iterdir()), ["run.mp4"])

    def test_failed_encode_keeps_the_original_recording(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            source = Path(raw) / "Screen Recording.mp4"
            source.write_bytes(b"r" * 1000)
            with mock.patch.object(fast_media.subprocess, "run", side_effect=fake_encoder(100, returncode=1)):
                kept = fast_media.shrink_video(source, Path(raw) / "run.mp4")
            self.assertEqual(kept.read_bytes(), b"r" * 1000)
            self.assertEqual(sorted(p.name for p in Path(raw).iterdir()), ["run.mp4"])

    def test_encode_that_is_not_smaller_keeps_the_original(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            source = Path(raw) / "run.mp4"
            source.write_bytes(b"r" * 100)
            with mock.patch.object(fast_media.subprocess, "run", side_effect=fake_encoder(500)):
                kept = fast_media.shrink_video(source)
            self.assertEqual(kept.read_bytes(), b"r" * 100)
            self.assertEqual(sorted(p.name for p in Path(raw).iterdir()), ["run.mp4"])

    def test_timeout_keeps_the_original(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            source = Path(raw) / "run.mp4"
            source.write_bytes(b"r" * 100)
            timeout = subprocess.TimeoutExpired(cmd="shrink", timeout=1)
            with mock.patch.object(fast_media.subprocess, "run", side_effect=timeout):
                self.assertEqual(fast_media.shrink_video(source).read_bytes(), b"r" * 100)

    def test_zero_long_side_skips_the_encode(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            source = Path(raw) / "raw.mov"
            source.write_bytes(b"r")
            with mock.patch.object(fast_media.subprocess, "run") as run:
                kept = fast_media.shrink_video(source, Path(raw) / "run.mp4", long_side=0)
            run.assert_not_called()
            self.assertEqual(kept.read_bytes(), b"r")

    def test_missing_source_is_returned_untouched(self) -> None:
        missing = Path(tempfile.gettempdir()) / "fast-media-missing.mp4"
        self.assertEqual(fast_media.shrink_video(missing), missing)


@unittest.skipUnless(shutil.which("swiftc"), "needs swiftc and AVFoundation")
class ShrinkVideoEncodeTests(unittest.TestCase):
    """Runs the real helper on a real clip, so an SDK change that breaks it shows up here."""

    def test_portrait_recording_comes_out_h264_at_review_size(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            clip = Path(raw) / "Screen Recording.mp4"
            make = fast_media.helper_command(MAKE_CLIP, name="test-clip")
            made = subprocess.run([*make, str(clip), "1290", "2796", "24"], capture_output=True, text=True, timeout=600)
            self.assertEqual(made.stdout.strip(), "ok", made.stderr)
            kept = fast_media.shrink_video(clip, Path(raw) / "run.mp4")
            info = fast_media.helper_command(CLIP_INFO, name="test-info")
            described = subprocess.run([*info, str(kept)], capture_output=True, text=True, timeout=120)
            self.assertEqual(kept, Path(raw) / "run.mp4")
            self.assertFalse(clip.exists())
            self.assertEqual(described.stdout.strip(), "442x960 avc1", described.stderr)


class DeviceRecordingTests(unittest.TestCase):
    def test_enable_recording_keeps_the_recording_of_a_passing_test(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            xctestrun = Path(raw) / "run.xctestrun"
            xctestrun.write_bytes(plistlib.dumps({fast_device.TEST_TARGET: {
                "SystemAttachmentLifetime": "deleteOnSuccess", "PreferredScreenCaptureFormat": "screenshots",
            }}))
            fast_device.enable_recording(xctestrun)
            target = plistlib.loads(xctestrun.read_bytes())[fast_device.TEST_TARGET]
        self.assertEqual(target["SystemAttachmentLifetime"], "keepAlways")
        self.assertEqual(target["PreferredScreenCaptureFormat"], "screenRecording")

    def test_publish_recording_names_the_passing_clip_final(self) -> None:
        with tempfile.TemporaryDirectory() as raw, \
                mock.patch.object(fast_device, "shrink_video", side_effect=lambda s, t=None: Path(shutil.move(str(s), t or s))):
            run = Path(raw) / "task" / "20261013-110324-00008120"
            run.mkdir(parents=True)
            (run / "Screen Recording 2026-10-13 at 11.03.mp4").write_bytes(b"v" * 10)
            (run / "1-paywall.png").write_bytes(b"p")
            (run / "result.xcresult").mkdir()
            video = fast_device.publish_recording(run, passed=True, session="qa")
            self.assertEqual(video, Path(raw) / "task" / "final-qa.mp4")
            self.assertTrue((run / "1-paywall.png").exists())
            self.assertFalse(list(run.glob("*.mp4")))

    def test_publish_recording_keeps_a_failing_clip_as_run_mp4(self) -> None:
        with tempfile.TemporaryDirectory() as raw, \
                mock.patch.object(fast_device, "shrink_video", side_effect=lambda s, t=None: Path(shutil.move(str(s), t or s))):
            run = Path(raw) / "task" / "20261013-110324-00008120"
            run.mkdir(parents=True)
            (run / "Screen Recording.mp4").write_bytes(b"v" * 10)
            video = fast_device.publish_recording(run, passed=False)
            self.assertEqual(video, run / "run.mp4")

    def test_publish_recording_without_a_recording_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            (Path(raw) / "shot.png").write_bytes(b"p")
            self.assertIsNone(fast_device.publish_recording(Path(raw), passed=True))

    def test_record_and_serve_are_refused_together(self) -> None:
        with self.assertRaises(SystemExit), mock.patch("sys.stderr"):
            fast_device.parse_flow_arguments(["flow.json", "--record", "--serve"])

    def test_session_defaults_to_the_shared_environment_variable(self) -> None:
        with mock.patch.dict(os.environ, {"FAST_UI_SESSION": "pr-12"}):
            self.assertEqual(fast_device.parse_flow_arguments(["flow.json"]).session, "pr-12")

    def test_record_is_refused_while_a_persistent_runner_holds_the_iphone(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            flow = Path(raw) / "flow.json"
            flow.write_text(json.dumps({"version": 1, "name": "f", "app": {"project_root": raw}, "actions": []}))
            device = {"udid": "00008120-AAAA", "name": "Test iPhone", "os": "26.6", "connected": True}
            with mock.patch.object(fast_device, "resolve_device", return_value=device), \
                    mock.patch.object(fast_device, "server_alive", return_value=True), \
                    mock.patch.object(fast_device, "run_one_shot") as one_shot:
                with self.assertRaisesRegex(fast_device.FastDeviceError, "--record needs a one-shot run"):
                    fast_device.run_flow(fast_device.parse_flow_arguments([str(flow), "--record"]))
            one_shot.assert_not_called()


class LauncherCopyTests(unittest.TestCase):
    """A zip (and some plugin installs) store bin/ launchers as copies, not symlinks."""

    def test_copied_launchers_still_find_the_shared_module(self) -> None:
        here = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            shutil.copytree(here, root / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
            (root / "bin").mkdir()
            for launcher, script in {
                "fastDeviceTest": "fast_device.py", "fastSimulatorTest": "fast_ui.py", "fastUIReview": "fast_ui_review.py", "fastUIMap": "fast_ui_map.py",
            }.items():
                shutil.copy(here / script, root / "bin" / launcher)
                with self.subTest(launcher=launcher):
                    ran = subprocess.run(
                        [sys.executable, str(root / "bin" / launcher), "--help"],
                        capture_output=True, text=True, timeout=60, cwd=raw,
                    )
                    self.assertEqual(ran.returncode, 0, ran.stderr[-300:])


class ReportTargetTests(unittest.TestCase):
    def test_device_runs_are_keyed_by_their_udid(self) -> None:
        self.assertEqual(fast_ui_report.target({"udid": "00008120-00041CD2"}), "00008120")
        self.assertEqual(fast_ui_report.target({"simulator": "ABCDEF12-3456"}), "ABCDEF12")
        self.assertEqual(fast_ui_report.target({}), "?")


if __name__ == "__main__":
    unittest.main(verbosity=1)
