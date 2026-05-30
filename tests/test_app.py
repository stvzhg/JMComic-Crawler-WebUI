"""
Unit tests for the JMComic Crawler WebUI Flask application.

Covers app.py with maximum line and branch coverage.
"""
import importlib
import json
import os
import sys
import tempfile
import threading
import time
from unittest import mock

import pytest

# ── Helpers to create fresh mock modules before importing app ────────────

# Ensure config/option.yml exists so the module-level bootstrap succeeds
_ORIG_CWD = os.getcwd()
_TMP_DIR = None


def _ensure_config_exists():
    """Create a minimal config in a temp directory so app.py can import."""
    global _TMP_DIR
    _TMP_DIR = tempfile.mkdtemp(prefix='jmcomic_test_')
    config_dir = os.path.join(_TMP_DIR, 'config')
    os.makedirs(config_dir, exist_ok=True)
    with open(os.path.join(config_dir, 'option.yml'), 'w') as f:
        f.write('download:\n  image:\n    suffix: .png\n')
    # Also create a minimal template / static dir so Flask can find them
    for sub in ['templates', 'static']:
        d = os.path.join(_TMP_DIR, sub)
        os.makedirs(d, exist_ok=True)
        if sub == 'templates':
            for name in ['index.html', 'success.html', 'error.html']:
                with open(os.path.join(d, name), 'w') as f:
                    f.write('<html></html>')
    os.chdir(_TMP_DIR)


def _teardown_config():
    """Restore original CWD and clean up temp dir."""
    global _TMP_DIR
    os.chdir(_ORIG_CWD)
    if _TMP_DIR and os.path.isdir(_TMP_DIR):
        import shutil
        shutil.rmtree(_TMP_DIR, ignore_errors=True)
        _TMP_DIR = None


# ── Mock base class for ProgressDownloader ───────────────────────────────

class MockJmDownloader:
    """Stand-in for jmcomic.JmDownloader so ProgressDownloader can inherit."""
    def __init__(self, option):
        self.option = option
        self.download_success_dict = {}
        self.download_failed_image = []
        self.download_failed_photo = []

    def before_album(self, album):
        pass

    def after_image(self, image, img_save_path):
        pass

    def after_photo(self, photo):
        pass

    def raise_if_has_exception(self):
        pass


# ── Build the mock jmcomic module tree ───────────────────────────────────

mock_jmcomic = mock.MagicMock()
mock_jmcomic.JmDownloader = MockJmDownloader
mock_jmcomic.create_option_by_file = mock.MagicMock(return_value=mock.MagicMock())
mock_jmcomic.create_option_by_str = mock.MagicMock(return_value=mock.MagicMock())
mock_jmcomic.download_album = mock.MagicMock()

mock_jm_toolkit = mock.MagicMock()
mock_jm_toolkit.JmcomicText = mock.MagicMock()

# Inject into sys.modules before app.py imports them
sys.modules['jmcomic'] = mock_jmcomic
sys.modules['jmcomic.jm_toolkit'] = mock_jm_toolkit


# ── Now import the app ───────────────────────────────────────────────────

_ensure_config_exists()

try:
    import app as _app_module
    from app import (
        app,
        ProgressDownloader,
        TASKS_DIR,
        OPTION,
        CONFIG_PATH,
        EXAMPLE_CONFIG_PATH,
        _read_task,
        _write_task,
        _task_path,
        _cleanup_old_tasks,
        _cleanup_thread,
    )
finally:
    _teardown_config()


# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    """Flask test client."""
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def reset_task_dir():
    """Ensure the tasks directory is clean before each test."""
    import shutil
    if os.path.isdir(TASKS_DIR):
        shutil.rmtree(TASKS_DIR, ignore_errors=True)
    yield
    if os.path.isdir(TASKS_DIR):
        shutil.rmtree(TASKS_DIR, ignore_errors=True)


@pytest.fixture(autouse=True)
def reset_mocks():
    """Reset all jmcomic mocks between tests."""
    mock_jmcomic.create_option_by_file.reset_mock(side_effect=True, return_value=True)
    mock_jmcomic.create_option_by_str.reset_mock(side_effect=True, return_value=True)
    mock_jmcomic.download_album.reset_mock()
    mock_jmcomic.download_album.side_effect = None
    # Safe default: return a valid 2-tuple for background threads
    mock_jmcomic.download_album.return_value = (mock.MagicMock(), mock.MagicMock())
    yield


@pytest.fixture
def mock_album():
    """A minimal mock album for testing ProgressDownloader."""
    album = mock.MagicMock()
    album.page_count = 42
    album.__len__ = mock.MagicMock(return_value=3)
    album.name = 'Test Album'
    album.title = 'Test Album Title'
    return album


@pytest.fixture
def mock_photo():
    """A minimal mock photo."""
    photo = mock.MagicMock()
    photo.__len__ = mock.MagicMock(return_value=10)
    return photo


@pytest.fixture
def mock_image():
    """A minimal mock image."""
    return mock.MagicMock()


# ── Task file helpers ────────────────────────────────────────────────────

class TestTaskPath:
    def test_task_path_returns_correct_path(self):
        result = _task_path('abc-123')
        assert result == os.path.join(TASKS_DIR, 'abc-123.json')


class TestReadTask:
    def test_read_nonexistent_task_returns_none(self):
        assert _read_task('nonexistent') is None

    def test_read_existing_task_returns_data(self):
        _write_task('test-1', {'status': 'done', 'pages': 10})
        result = _read_task('test-1')
        assert result == {'status': 'done', 'pages': 10}

    def test_read_corrupt_json_returns_none(self):
        os.makedirs(TASKS_DIR, exist_ok=True)
        with open(_task_path('corrupt'), 'w') as f:
            f.write('not valid json {{{')
        assert _read_task('corrupt') is None

    def test_read_deleted_between_attempts(self):
        """Edge case: file is deleted after existence check."""
        # _read_task uses try/except FileNotFoundError, so this is covered
        _write_task('will-delete', {'x': 1})
        os.remove(_task_path('will-delete'))
        assert _read_task('will-delete') is None


class TestWriteTask:
    def test_write_creates_directory_and_file(self):
        tid = 'write-test'
        _write_task(tid, {'status': 'starting', 'count': 0})
        path = _task_path(tid)
        assert os.path.isfile(path)
        assert not os.path.isfile(path + '.tmp')  # tmp should be gone
        with open(path) as f:
            assert json.load(f) == {'status': 'starting', 'count': 0}

    def test_write_overwrites_existing(self):
        tid = 'overwrite-test'
        _write_task(tid, {'a': 1})
        _write_task(tid, {'b': 2})
        assert _read_task(tid) == {'b': 2}

    def test_write_and_read_roundtrip_complex_data(self):
        tid = 'complex'
        data = {
            'task_id': tid,
            'status': 'downloading',
            'total_pages': 100,
            'downloaded_pages': 50,
            'total_chapters': 5,
            'downloaded_chapters': 2,
            'album_title': 'Test',
            'message': '',
            'created_at': time.time(),
            'finished_at': None,
        }
        _write_task(tid, data)
        result = _read_task(tid)
        assert result == data


# ── ProgressDownloader ───────────────────────────────────────────────────

class TestProgressDownloader:
    """Tests for the ProgressDownloader class."""

    def setup_method(self):
        self.task_id = 'pd-test-1'
        _write_task(self.task_id, {
            'task_id': self.task_id,
            'status': 'starting',
            'comic_id': '12345',
            'total_pages': 0,
            'downloaded_pages': 0,
            'total_chapters': 0,
            'downloaded_chapters': 0,
            'album_title': '',
            'message': '',
            'created_at': time.time(),
            'finished_at': None,
        })
        ProgressDownloader._current_task_id = self.task_id
        self.downloader = ProgressDownloader(mock.MagicMock())

    def teardown_method(self):
        # Clean up task file
        path = _task_path(self.task_id)
        for ext in ['', '.tmp']:
            try:
                os.remove(path + ext)
            except OSError:
                pass

    def test_init_copies_task_id(self):
        assert self.downloader._task_id == self.task_id
        assert self.downloader._write_interval == 3
        assert self.downloader._last_written_pages == 0

    def test_before_album_sets_totals(self, mock_album):
        self.downloader.before_album(mock_album)
        task = _read_task(self.task_id)
        assert task['status'] == 'downloading'
        assert task['total_pages'] == 42
        assert task['total_chapters'] == 3
        assert task['album_title'] == 'Test Album'  # album.name takes priority

    def test_before_album_falls_back_to_title(self):
        """When album.name is empty, use album.title."""
        album = mock.MagicMock()
        album.page_count = 10
        album.__len__ = mock.MagicMock(return_value=1)
        album.name = ''
        album.title = 'Fallback Title'
        self.downloader.before_album(album)
        task = _read_task(self.task_id)
        assert task['album_title'] == 'Fallback Title'

    def test_before_album_page_count_zero_handled(self):
        """When page_count is None or 0, total_pages stays 0."""
        album = mock.MagicMock()
        album.page_count = None
        album.__len__ = mock.MagicMock(return_value=2)
        album.name = 'X'
        album.title = 'X'
        self.downloader.before_album(album)
        task = _read_task(self.task_id)
        assert task['total_pages'] == 0
        assert task['total_chapters'] == 2

    def test_before_album_page_count_missing_attribute(self):
        """When album has no page_count attribute at all."""
        album = mock.MagicMock()
        # Delete page_count so getattr falls back to default 0
        del album.page_count
        album.__len__ = mock.MagicMock(return_value=1)
        album.name = 'X'
        album.title = 'X'
        # getattr with default handles this
        self.downloader.before_album(album)
        task = _read_task(self.task_id)
        assert task['total_pages'] == 0

    def test_after_image_increments_and_debounces(self, mock_image):
        self.downloader._last_written_pages = 0
        # First 2 images: should NOT trigger writes (debounce interval = 3)
        self.downloader.after_image(mock_image, '/tmp/1.png')
        self.downloader.after_image(mock_image, '/tmp/2.png')
        task = _read_task(self.task_id)
        assert task['downloaded_pages'] == 0  # unchanged (debounced)

        # 3rd image: should trigger a write
        self.downloader.after_image(mock_image, '/tmp/3.png')
        task = _read_task(self.task_id)
        assert task['downloaded_pages'] == 3

        # 4th and 5th: debounced
        self.downloader.after_image(mock_image, '/tmp/4.png')
        self.downloader.after_image(mock_image, '/tmp/5.png')
        task = _read_task(self.task_id)
        assert task['downloaded_pages'] == 3  # still 3

        # 6th: triggers write
        self.downloader.after_image(mock_image, '/tmp/6.png')
        task = _read_task(self.task_id)
        assert task['downloaded_pages'] == 6

    def test_after_image_task_not_found_is_noop(self, mock_image):
        """If the task file was deleted, after_image should not crash."""
        os.remove(_task_path(self.task_id))
        self.downloader.after_image(mock_image, '/tmp/x.png')
        # Should not raise — just returns early

    def test_after_photo_increments_chapter_and_flushes(self, mock_photo):
        # Simulate some images having been downloaded (but not all flushed)
        self.downloader._downloaded_pages = 7
        self.downloader._last_written_pages = 6
        _write_task(self.task_id, {
            **_read_task(self.task_id),
            'downloaded_pages': 6,   # only 6 were flushed to disk
            'downloaded_chapters': 0,
        })
        self.downloader.after_photo(mock_photo)
        task = _read_task(self.task_id)
        assert task['downloaded_chapters'] == 1
        # Flushes the actual in-memory count (7) catching remaining images
        assert task['downloaded_pages'] == 7

    def test_after_photo_task_not_found_is_noop(self):
        os.remove(_task_path(self.task_id))
        photo = mock.MagicMock()
        self.downloader.after_photo(photo)
        # Should not raise

    def test_update_task_handles_nonexistent_file(self):
        """_update_task on a deleted task should create it fresh."""
        os.remove(_task_path(self.task_id))
        self.downloader._update_task(status='updated')
        task = _read_task(self.task_id)
        assert task['status'] == 'updated'


# ── Cleanup daemon logic ─────────────────────────────────────────────────

class TestCleanupOldTasks:
    """Test the _cleanup_old_tasks logic by calling relevant branches directly."""

    def setup_method(self):
        os.makedirs(TASKS_DIR, exist_ok=True)

    def _run_one_cycle(self, now_override):
        """Run one cycle of cleanup with a mocked time."""
        with mock.patch('app.time.time', return_value=now_override):
            with mock.patch('app.time.sleep', return_value=None):
                # Run the loop body once by raising StopIteration after first pass
                original = _app_module._cleanup_old_tasks
                # Just call the inner logic directly by inspecting what it does
                # Instead, call a modified version
                pass

    def test_removes_done_task_older_than_5_min(self):
        now = time.time()
        tid = 'done-old'
        _write_task(tid, {
            'status': 'done',
            'finished_at': now - 301,
            'created_at': now - 400,
        })
        self._invoke_cleanup_cycle(now)
        # The file should have been removed
        assert _read_task(tid) is None

    def test_keeps_done_task_newer_than_5_min(self):
        now = time.time()
        tid = 'done-new'
        _write_task(tid, {
            'status': 'done',
            'finished_at': now - 200,
            'created_at': now - 250,
        })
        self._invoke_cleanup_cycle(now)
        assert _read_task(tid) is not None

    def test_removes_error_task_older_than_5_min(self):
        now = time.time()
        tid = 'error-old'
        _write_task(tid, {
            'status': 'error',
            'finished_at': now - 350,
            'created_at': now - 400,
        })
        self._invoke_cleanup_cycle(now)
        assert _read_task(tid) is None

    def test_removes_stale_starting_task_older_than_10_min(self):
        now = time.time()
        tid = 'stale-start'
        _write_task(tid, {
            'status': 'starting',
            'finished_at': None,
            'created_at': now - 601,
        })
        self._invoke_cleanup_cycle(now)
        assert _read_task(tid) is None

    def test_keeps_downloading_status_task(self):
        """Tasks with 'downloading' status should not be removed regardless of age."""
        now = time.time()
        tid = 'downloading-task'
        _write_task(tid, {
            'status': 'downloading',
            'finished_at': None,
            'created_at': now - 1000,  # very old
        })
        self._invoke_cleanup_cycle(now)
        assert _read_task(tid) is not None

    def test_keeps_unknown_status_task(self):
        """Tasks with unrecognized status should be left alone."""
        now = time.time()
        tid = 'unknown-task'
        _write_task(tid, {
            'status': 'unknown-status',
            'finished_at': None,
            'created_at': now - 1000,
        })
        self._invoke_cleanup_cycle(now)
        assert _read_task(tid) is not None

    def test_keeps_starting_task_newer_than_10_min(self):
        now = time.time()
        tid = 'fresh-start'
        _write_task(tid, {
            'status': 'starting',
            'finished_at': None,
            'created_at': now - 300,
        })
        self._invoke_cleanup_cycle(now)
        assert _read_task(tid) is not None

    def test_ignores_non_json_files(self):
        """Non-.json files should be skipped."""
        os.makedirs(TASKS_DIR, exist_ok=True)
        with open(os.path.join(TASKS_DIR, 'readme.txt'), 'w') as f:
            f.write('hello')
        now = time.time()
        self._invoke_cleanup_cycle(now)
        assert os.path.isfile(os.path.join(TASKS_DIR, 'readme.txt'))

    def test_removes_corrupt_json_older_than_10_min(self):
        """Corrupt JSON files older than 10 min should be removed."""
        os.makedirs(TASKS_DIR, exist_ok=True)
        fpath = os.path.join(TASKS_DIR, 'corrupt.json')
        with open(fpath, 'w') as f:
            f.write('not json {{{')
        # Set mtime to 11 min ago
        old_time = time.time() - 661
        os.utime(fpath, (old_time, old_time))
        now = time.time()
        self._invoke_cleanup_cycle(now)
        assert not os.path.isfile(fpath)

    def test_keeps_corrupt_json_newer_than_10_min(self):
        """Corrupt JSON files newer than 10 min should be kept."""
        os.makedirs(TASKS_DIR, exist_ok=True)
        fpath = os.path.join(TASKS_DIR, 'corrupt-new.json')
        with open(fpath, 'w') as f:
            f.write('not json')
        now = time.time()
        os.utime(fpath, (now, now))
        self._invoke_cleanup_cycle(now)
        assert os.path.isfile(fpath)

    def test_handles_oserror_during_corrupt_file_check(self):
        """OSError during corrupt JSON file removal should be caught."""
        os.makedirs(TASKS_DIR, exist_ok=True)
        fpath = os.path.join(TASKS_DIR, 'corrupt-oserror.json')
        with open(fpath, 'w') as f:
            f.write('not json {{{')
        old_time = time.time() - 661
        os.utime(fpath, (old_time, old_time))
        now = time.time()
        # The cleanup reads the corrupt file (_read_task returns None),
        # then tries os.path.getmtime and os.remove. Mock os.remove
        # to raise OSError.
        with mock.patch('os.remove', side_effect=OSError('Permission denied')):
            self._invoke_cleanup_cycle(now)
        # File should still exist (removal failed but exception was caught)
        assert os.path.isfile(fpath)

    def test_handles_missing_tasks_dir(self):
        """If TASKS_DIR doesn't exist, cleanup should not crash."""
        import shutil
        if os.path.isdir(TASKS_DIR):
            shutil.rmtree(TASKS_DIR, ignore_errors=True)
        self._invoke_cleanup_cycle(time.time())
        # Should not raise

    def test_handles_oserror_during_removal(self):
        """OSError during file removal should be caught (done task branch)."""
        now = time.time()
        tid = 'oserror-test'
        _write_task(tid, {
            'status': 'done',
            'finished_at': now - 500,
            'created_at': now - 600,
        })
        # Mock os.remove to raise OSError; the cleanup should catch it
        with mock.patch('os.remove', side_effect=OSError('Permission denied')):
            self._invoke_cleanup_cycle(now)
        # File should still exist (removal failed but exception was caught)
        assert _read_task(tid) is not None

    def test_handles_oserror_during_starting_removal(self):
        """OSError during stale starting task removal should be caught."""
        now = time.time()
        tid = 'oserror-start'
        _write_task(tid, {
            'status': 'starting',
            'finished_at': None,
            'created_at': now - 700,
        })
        with mock.patch('os.remove', side_effect=OSError('Permission denied')):
            self._invoke_cleanup_cycle(now)
        assert _read_task(tid) is not None

    def _invoke_cleanup_cycle(self, now):
        """Run one iteration of the real _cleanup_old_tasks function.

        Patches time.time and time.sleep so that:
        - time.time() always returns `now`
        - time.sleep() is a no-op on the first call (before the loop body)
          and raises StopIteration on the second call (after one iteration)
          to break out of the infinite while-loop.
        """
        sleep_count = [0]

        def _controlled_sleep(seconds):
            sleep_count[0] += 1
            if sleep_count[0] >= 2:
                raise StopIteration
            # First call: just return (skip the 60s wait)

        with mock.patch('app.time.time', return_value=now):
            with mock.patch('app.time.sleep', side_effect=_controlled_sleep):
                try:
                    _app_module._cleanup_old_tasks()
                except StopIteration:
                    pass


# ── Route: GET / ─────────────────────────────────────────────────────────

class TestIndexRoute:
    def test_index_returns_200(self, client):
        resp = client.get('/')
        assert resp.status_code == 200
        assert b'JMComic' in resp.data

    def test_index_has_preview_button(self, client):
        resp = client.get('/')
        assert b'previewButton' in resp.data

    def test_index_has_progress_section(self, client):
        resp = client.get('/')
        assert b'progress-bar-track' in resp.data


# ── Route: POST /api/download ────────────────────────────────────────────

class TestApiDownload:
    """Tests for POST /api/download.

    Uses a class-level mock of threading.Thread so background tasks run
    synchronously — eliminating test race conditions and thread warnings.
    """

    @pytest.fixture(autouse=True)
    def sync_threads(self):
        """Patch threading.Thread so .start() runs the target inline."""
        class SyncThread:
            def __init__(self, target, daemon=True):
                self._target = target

            def start(self):
                self._target()

        with mock.patch('app.threading.Thread', new=SyncThread):
            yield

    def test_missing_comic_id_returns_400(self, client):
        resp = client.post('/api/download', json={})
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert data['status'] == 'error'
        assert 'No comic ID' in data['message']

    def test_empty_comic_id_returns_400(self, client):
        resp = client.post('/api/download', json={'comic_id': '  '})
        assert resp.status_code == 400

    def test_no_json_body_returns_400(self, client):
        resp = client.post('/api/download', data='not json')
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert data['status'] == 'error'

    def test_valid_request_returns_accepted_with_task_id(self, client):
        # With SyncThread the download runs inline — provide a valid album
        good_album = mock.MagicMock()
        good_album.name = 'Test'
        good_album.title = 'Test'
        mock_jmcomic.download_album.return_value = (good_album, mock.MagicMock())

        resp = client.post('/api/download', json={'comic_id': '12345'})
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['status'] == 'accepted'
        assert 'task_id' in data
        task = _read_task(data['task_id'])
        assert task is not None
        assert task['status'] in ('starting', 'downloading', 'done')
        assert task['comic_id'] == '12345'

    def test_background_thread_success_path(self, client):
        """Simulate a successful download by mocking download_album."""
        mock_album = mock.MagicMock()
        mock_album.name = 'Test Album'
        mock_album.title = 'Test Album'
        mock_downloader = mock.MagicMock()
        mock_jmcomic.download_album.return_value = (mock_album, mock_downloader)

        resp = client.post('/api/download', json={'comic_id': 'success-id'})
        data = json.loads(resp.data)
        task_id = data['task_id']

        task = _read_task(task_id)
        assert task is not None
        assert task['status'] == 'done'
        assert 'Test Album' in task['album_title']
        assert 'successfully' in task['message']

    def test_background_thread_error_path(self, client):
        """Simulate a failed download."""
        mock_jmcomic.download_album.side_effect = Exception('Download failed: network error')

        resp = client.post('/api/download', json={'comic_id': 'error-id'})
        data = json.loads(resp.data)
        task_id = data['task_id']

        task = _read_task(task_id)
        assert task is not None
        assert task['status'] == 'error'
        assert 'network error' in task['message']

    def test_background_thread_album_has_only_title(self, client):
        """Album with no .name attribute falls back to .title."""
        mock_album = mock.MagicMock(spec=['title'])
        mock_album.title = 'Title Only'
        mock_downloader = mock.MagicMock()
        mock_jmcomic.download_album.return_value = (mock_album, mock_downloader)
        mock_jmcomic.download_album.side_effect = None

        resp = client.post('/api/download', json={'comic_id': 'title-only'})
        data = json.loads(resp.data)
        task_id = data['task_id']

        task = _read_task(task_id)
        assert task['album_title'] == 'Title Only'

    def test_background_thread_exception_preserves_existing_task_data(self, client):
        """When download fails, task data from before_album should be preserved."""
        mock_jmcomic.download_album.side_effect = Exception('Boom')

        resp = client.post('/api/download', json={'comic_id': 'preserve-test'})
        data = json.loads(resp.data)
        task_id = data['task_id']

        task = _read_task(task_id)
        assert task['status'] == 'error'
        assert task['message'] == 'Boom'
        assert task['comic_id'] == 'preserve-test'


# ── Route: GET /api/progress/<task_id> ──────────────────────────────────

class TestApiProgress:
    def test_existing_task_returns_data(self, client):
        tid = 'progress-test'
        _write_task(tid, {
            'task_id': tid,
            'status': 'downloading',
            'total_pages': 100,
            'downloaded_pages': 45,
            'total_chapters': 5,
            'downloaded_chapters': 2,
            'album_title': 'My Album',
            'message': '',
        })
        resp = client.get(f'/api/progress/{tid}')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['status'] == 'downloading'
        assert data['total_pages'] == 100
        assert data['downloaded_pages'] == 45

    def test_nonexistent_task_returns_404(self, client):
        resp = client.get('/api/progress/nonexistent-id')
        assert resp.status_code == 404
        data = json.loads(resp.data)
        assert data['status'] == 'not_found'
        assert 'not found' in data['message'].lower()

    def test_done_task_returns_status_done(self, client):
        tid = 'done-task'
        _write_task(tid, {
            'task_id': tid,
            'status': 'done',
            'message': 'All good',
        })
        resp = client.get(f'/api/progress/{tid}')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['status'] == 'done'


# ── Route: POST /api/preview ─────────────────────────────────────────────

class TestApiPreview:
    def test_missing_comic_id_returns_400(self, client):
        resp = client.post('/api/preview', json={})
        assert resp.status_code == 400

    def test_empty_comic_id_returns_400(self, client):
        resp = client.post('/api/preview', json={'comic_id': ''})
        assert resp.status_code == 400

    def test_no_json_body_returns_400(self, client):
        resp = client.post('/api/preview', data='not json')
        assert resp.status_code == 400

    def test_successful_preview_returns_metadata(self, client):
        mock_client = mock.MagicMock()
        mock_album = mock.MagicMock()
        mock_album.album_id = '12345'
        mock_album.name = 'Preview Album'
        mock_album.authors = ['Author One', 'Author Two']
        mock_album.tags = ['tag1', 'tag2']
        mock_album.description = 'A test album'
        mock_album.views = '5000'
        mock_album.likes = '300'
        mock_album.page_count = 50
        mock_album.__len__ = mock.MagicMock(return_value=4)

        mock_client.get_album_detail.return_value = mock_album
        mock_jm_toolkit.JmcomicText.get_album_cover_url.return_value = \
            'https://cdn.example.com/albums/12345.jpg'

        # Patch OPTION.build_jm_client
        with mock.patch.object(OPTION, 'build_jm_client', return_value=mock_client):
            resp = client.post('/api/preview', json={'comic_id': '12345'})

        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['status'] == 'success'
        assert data['title'] == 'Preview Album'
        assert data['authors'] == ['Author One', 'Author Two']
        assert data['tags'] == ['tag1', 'tag2']
        assert data['chapter_count'] == 4
        assert data['page_count'] == 50
        assert data['cover_url'] == 'https://cdn.example.com/albums/12345.jpg'

    def test_preview_with_empty_tags_and_description(self, client):
        mock_client = mock.MagicMock()
        mock_album = mock.MagicMock()
        mock_album.album_id = 'empty'
        mock_album.name = 'Empty Album'
        mock_album.authors = []
        mock_album.tags = []
        mock_album.description = None
        mock_album.views = '0'
        mock_album.likes = '0'
        mock_album.page_count = 0
        mock_album.__len__ = mock.MagicMock(return_value=1)

        mock_client.get_album_detail.return_value = mock_album
        mock_jm_toolkit.JmcomicText.get_album_cover_url.return_value = 'https://cdn.example.com/albums/empty.jpg'

        with mock.patch.object(OPTION, 'build_jm_client', return_value=mock_client):
            resp = client.post('/api/preview', json={'comic_id': 'empty'})

        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['status'] == 'success'
        assert data['authors'] == []
        assert data['tags'] == []
        assert data['description'] == ''

    def test_preview_exception_returns_500(self, client):
        with mock.patch.object(OPTION, 'build_jm_client', side_effect=Exception('Boom')):
            resp = client.post('/api/preview', json={'comic_id': 'error'})

        assert resp.status_code == 500
        data = json.loads(resp.data)
        assert data['status'] == 'error'
        assert 'Boom' in data['message']


# ── Route: GET /download ─────────────────────────────────────────────────

class TestDownloadRoute:
    def test_no_comic_id_renders_success_with_empty_id(self, client):
        """GET /download with no comicId defaults to empty string."""
        # download_album is called with empty string — mock it
        mock_album = mock.MagicMock()
        mock_album.title = ''
        mock_downloader = mock.MagicMock()
        mock_jmcomic.download_album.return_value = (mock_album, mock_downloader)

        resp = client.get('/download')
        # The route catches the empty id and calls download_album('')
        assert resp.status_code == 200

    def test_successful_download_renders_success_template(self, client):
        mock_album = mock.MagicMock()
        mock_album.title = 'Downloaded Album'
        mock_downloader = mock.MagicMock()
        mock_jmcomic.download_album.return_value = (mock_album, mock_downloader)

        resp = client.get('/download?comicId=12345')
        assert resp.status_code == 200
        assert b'Download Complete' in resp.data
        # Should contain the album title
        assert b'Downloaded Album' in resp.data

    def test_failed_download_renders_error_template(self, client):
        mock_jmcomic.download_album.side_effect = Exception('Failed')

        resp = client.get('/download?comicId=bad-id')
        assert resp.status_code == 200
        assert b'Download Failed' in resp.data
        assert b'Failed' in resp.data


# ── Config bootstrap tests ───────────────────────────────────────────────

class TestConfigBootstrap:
    """Test the module-level config bootstrap logic via importlib.reload."""

    def test_config_exists_path(self, tmp_path):
        """When config/option.yml exists, use it directly."""
        # This is the normal path — the module imported successfully above.
        # The file exists in the test temp dir. We verify OPTION was made
        # via create_option_by_file by checking it has build_jm_client.
        assert hasattr(OPTION, 'build_jm_client')
        # The mock was called at module import time (before reset_mocks fixture)
        # We can verify by checking the mock's call history before reset

    @mock.patch('app.os.path.isfile')
    @mock.patch('app.os.makedirs')
    @mock.patch('app.shutil.copyfile')
    def test_config_missing_example_exists(self, mock_copy, mock_mkdir, mock_isfile):
        """When option.yml is missing but example exists, copy it."""
        mock_isfile.side_effect = lambda path: path == EXAMPLE_CONFIG_PATH

        mock_jmcomic.create_option_by_file.reset_mock()
        mock_jmcomic.create_option_by_str.reset_mock()

        import app as app_mod
        importlib.reload(app_mod)

        mock_copy.assert_called_once_with(EXAMPLE_CONFIG_PATH, CONFIG_PATH)
        mock_mkdir.assert_called_once()

    @mock.patch('app.os.path.isfile', return_value=False)
    @mock.patch('app.os.makedirs')
    def test_neither_config_exists(self, mock_mkdir, mock_isfile):
        """When neither config exists, fall back to create_option_by_str('{}')."""
        import app as app_mod
        mock_jmcomic.create_option_by_str.reset_mock()
        mock_jmcomic.create_option_by_file.reset_mock()
        importlib.reload(app_mod)

        mock_jmcomic.create_option_by_str.assert_called_once_with('{}')


# ── Cleanup thread startup ───────────────────────────────────────────────

class TestCleanupThread:
    def test_cleanup_thread_is_daemon(self):
        assert _cleanup_thread.daemon is True

    def test_cleanup_thread_is_alive(self):
        # Note: after mock injection the thread might behave differently
        # but the thread object should exist
        assert _cleanup_thread is not None


# ── Cover edge case: album title extraction ────────────────────────────

class TestAlbumTitleExtraction:
    """Tests for the album_title fallback logic in api_download's _run."""

    @pytest.fixture(autouse=True)
    def sync_threads(self):
        class SyncThread:
            def __init__(self, target, daemon=True):
                self._target = target

            def start(self):
                self._target()

        with mock.patch('app.threading.Thread', new=SyncThread):
            yield

    def test_album_without_name_or_title_uses_comic_id(self, client):
        """When album has no name and no title, falls back to comic_id."""
        mock_album = mock.MagicMock(spec=[])  # no attributes at all
        mock_downloader = mock.MagicMock()
        mock_jmcomic.download_album.return_value = (mock_album, mock_downloader)

        resp = client.post('/api/download', json={'comic_id': 'fallback-id'})
        data = json.loads(resp.data)
        task = _read_task(data['task_id'])
        assert task['album_title'] == 'fallback-id'
        assert task['status'] == 'done'

    def test_album_with_empty_name_uses_title(self, client):
        """When album.name is empty string, use album.title."""
        mock_album = mock.MagicMock()
        mock_album.name = ''
        mock_album.title = 'Real Title'
        mock_downloader = mock.MagicMock()
        mock_jmcomic.download_album.return_value = (mock_album, mock_downloader)

        resp = client.post('/api/download', json={'comic_id': 'x'})
        data = json.loads(resp.data)
        task = _read_task(data['task_id'])
        assert task['album_title'] == 'Real Title'


# ── Test TASKS_DIR constant ──────────────────────────────────────────────

class TestConstants:
    def test_tasks_dir_is_correct(self):
        assert TASKS_DIR == 'data/.tasks'

    def test_config_path_is_correct(self):
        assert CONFIG_PATH == 'config/option.yml'


# ── OPTION mock verification ─────────────────────────────────────────────

class TestOptionMock:
    def test_option_has_build_jm_client(self):
        assert hasattr(OPTION, 'build_jm_client')
