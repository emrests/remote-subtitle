from rsub.capture import list_sources, pick_window, snapshot_jpeg, target_rect, to_pixels


def test_to_pixels_scales_with_window():
    assert to_pixels([0.0, 0.7, 1.0, 0.3], (100, 50, 1000, 500)) == {"left": 100, "top": 400, "width": 1000, "height": 150}


def test_to_pixels_negative_monitor():
    assert to_pixels([0.5, 0.5, 0.5, 0.5], (-2560, 471, 2560, 1600))["left"] == -1280


def test_to_pixels_min_size():
    box = to_pixels([0.5, 0.5, 0.0, 0.0], (0, 0, 100, 100))
    assert box["width"] >= 1 and box["height"] >= 1


def test_monitor_source_resolves():
    assert target_rect("monitor:1") is not None


def test_unknown_window_is_none():
    assert target_rect("no-such-window-xyz") is None
    assert target_rect("monitor:99") is None


def test_list_sources_has_monitors():
    ids = [s["id"] for s in list_sources()]
    assert "monitor:1" in ids


def test_snapshot_is_small_jpeg():
    jpg, w, h = snapshot_jpeg("monitor:1")
    assert jpg[:2] == bytes([0xFF, 0xD8]) and w > 0 and h > 0 and len(jpg) < 1_000_000


def test_pick_window_prefers_exact_then_prefix():
    wins = [(1, "chiaki-ng releases - Google Chrome"), (2, "chiaki-ng"), (3, "Chiaki-ng | Stream")]
    assert pick_window(wins, "chiaki-ng") == 2
    assert pick_window([wins[0], wins[2]], "chiaki-ng") == 3
    assert pick_window(wins[:1], "chiaki-ng") == 1
    assert pick_window(wins, "") is None and pick_window(wins, "  ") is None


def test_list_sources_hides_shell_windows():
    assert "Program Manager" not in [s["id"] for s in list_sources()]


def test_video_frame_letterboxed_in_wider_window():
    from rsub.capture import video_frame
    # 2560x1600 (16:10) pencerede 16:9 video: üst/alt siyah şerit
    assert video_frame((-2560, 471, 2560, 1600)) == (-2560, 471 + 80, 2560, 1440)
    # 1920x1080 zaten 16:9
    assert video_frame((0, 0, 1920, 1080)) == (0, 0, 1920, 1080)
    # daha dar pencere: yanlarda şerit
    assert video_frame((0, 0, 1000, 1000)) == (0, 219, 1000, 562)
