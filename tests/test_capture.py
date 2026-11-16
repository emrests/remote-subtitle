from rsub.capture import list_sources, snapshot_png, target_rect, to_pixels


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


def test_snapshot_png():
    png, w, h = snapshot_png("monitor:1")
    assert png[:4] == b"\x89PNG" and w > 0 and h > 0


def test_list_sources_hides_shell_windows():
    assert "Program Manager" not in [s["id"] for s in list_sources()]
