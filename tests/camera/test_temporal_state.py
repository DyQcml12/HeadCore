from datetime import UTC, datetime, timedelta

from app.camera.contracts import CameraObservation
from app.camera.temporal_state import CameraTemporalState


def observation(*, when: datetime, objects: tuple[str, ...] = ("book",)) -> CameraObservation:
    return CameraObservation(
        session_id="cam_" + "a" * 32,
        objects=objects,
        pose_labels=("sitting",),
        confidence=0.9,
        observed_at=when,
    )


def test_temporal_state_requires_repeated_observation_before_confirmation() -> None:
    state = CameraTemporalState(confirmation_count=2, window_seconds=8)
    now = datetime(2026, 7, 23, tzinfo=UTC)

    assert state.observe(observation(when=now)) is None
    stable = state.observe(observation(when=now + timedelta(seconds=2)))

    assert stable is not None
    assert stable.observation.objects == ("book",)
    assert stable.observation.pose_labels == ("sitting",)
    assert stable.changes == ("appeared:objects:book", "appeared:pose_labels:sitting")


def test_temporal_state_reports_only_confirmed_appearance_and_disappearance() -> None:
    state = CameraTemporalState(confirmation_count=2, window_seconds=8)
    now = datetime(2026, 7, 23, tzinfo=UTC)
    state.observe(observation(when=now))
    state.observe(observation(when=now + timedelta(seconds=1)))

    assert state.observe(observation(when=now + timedelta(seconds=2), objects=("book", "phone"))).changes == ()
    appeared = state.observe(observation(when=now + timedelta(seconds=3), objects=("book", "phone")))
    assert appeared is not None
    assert "appeared:objects:phone" in appeared.changes

    assert state.observe(observation(when=now + timedelta(seconds=4), objects=("phone",))).changes == ()
    disappeared = state.observe(observation(when=now + timedelta(seconds=5), objects=("phone",)))
    assert disappeared is not None
    assert "disappeared:objects:book" in disappeared.changes


def test_temporal_state_does_not_confirm_observation_outside_window() -> None:
    state = CameraTemporalState(confirmation_count=2, window_seconds=8)
    now = datetime(2026, 7, 23, tzinfo=UTC)

    assert state.observe(observation(when=now)) is None
    assert state.observe(observation(when=now + timedelta(seconds=9))) is None


def test_temporal_state_clears_history_when_session_stops() -> None:
    state = CameraTemporalState(confirmation_count=2, window_seconds=8)
    now = datetime(2026, 7, 23, tzinfo=UTC)
    state.observe(observation(when=now))

    state.remove_session("cam_" + "a" * 32)

    assert state.observe(observation(when=now + timedelta(seconds=1))) is None
    assert state.latest("cam_" + "a" * 32) is None


def test_temporal_state_exposes_only_the_latest_stable_update() -> None:
    state = CameraTemporalState(confirmation_count=2, window_seconds=8)
    now = datetime(2026, 7, 23, tzinfo=UTC)
    state.observe(observation(when=now))
    expected = state.observe(observation(when=now + timedelta(seconds=1)))

    assert state.latest("cam_" + "a" * 32) == expected
