(function () {
    'use strict';

    var form = document.getElementById('submissionForm');
    var loading = document.getElementById('loading');
    var loadingText = document.getElementById('loadingText');
    var result = document.getElementById('result');
    var resultMessage = document.getElementById('resultMessage');
    var resetButton = document.getElementById('resetButton');
    var submitButton = document.getElementById('submitButton');
    var previewButton = document.getElementById('previewButton');
    var comicIdInput = document.getElementById('comicId');

    // Preview card elements
    var preview = document.getElementById('preview');
    var previewCover = document.getElementById('previewCover');
    var previewTitleEl = document.getElementById('previewTitle');
    var previewAuthors = document.getElementById('previewAuthors');
    var previewTags = document.getElementById('previewTags');
    var previewDescription = document.getElementById('previewDescription');
    var previewViews = document.getElementById('previewViews');
    var previewLikes = document.getElementById('previewLikes');
    var previewPages = document.getElementById('previewPages');
    var previewChapters = document.getElementById('previewChapters');
    var previewDownloadBtn = document.getElementById('previewDownloadButton');
    var previewCancelBtn = document.getElementById('previewCancelButton');

    // Progress elements
    var progress = document.getElementById('progress');
    var progressBar = document.getElementById('progressBar');
    var progressTitle = document.getElementById('progressTitle');
    var progressStats = document.getElementById('progressStats');

    // If any required element is missing, bail out (graceful degradation)
    if (!form || !loading || !result || !resetButton || !submitButton || !comicIdInput) {
        return;
    }

    // Track polling state
    var pollTimer = null;
    var pollStartTime = 0;

    /**
     * Stop any active progress polling.
     */
    function stopPolling() {
        if (pollTimer) {
            clearInterval(pollTimer);
            pollTimer = null;
        }
    }

    /**
     * Transition UI to the loading state.
     * @param {string} [message='Loading, please wait…']
     */
    function showLoading(message) {
        stopPolling();
        form.classList.add('hidden');
        result.classList.add('hidden');
        if (preview) { preview.classList.add('hidden'); }
        if (progress) { progress.classList.add('hidden'); }
        loadingText.textContent = message || 'Loading, please wait…';
        loading.classList.remove('hidden');
        submitButton.disabled = true;
        if (previewButton) { previewButton.disabled = true; }
    }

    /**
     * Transition UI to the progress state.
     */
    function showProgressView() {
        loading.classList.add('hidden');
        result.classList.add('hidden');
        if (preview) { preview.classList.add('hidden'); }
        progressTitle.textContent = 'Downloading…';
        progressBar.style.width = '0%';
        progressStats.textContent = '0 / ? pages  |  0 / ? chapters';
        if (progress) { progress.classList.remove('hidden'); }
    }

    /**
     * Update the progress bar and counters from polled task data.
     * @param {object} data — response from GET /api/progress/<task_id>
     */
    function updateProgress(data) {
        var pct = data.total_pages > 0
            ? Math.round((data.downloaded_pages / data.total_pages) * 100)
            : 0;
        progressBar.style.width = Math.min(pct, 100) + '%';

        if (data.album_title) {
            progressTitle.textContent = data.album_title;
        }

        var pagesText = data.downloaded_pages + ' / ' + (data.total_pages || '?') + ' pages';
        var chaptersText = data.downloaded_chapters + ' / ' + (data.total_chapters || '?') + ' chapters';
        progressStats.textContent = pagesText + '  |  ' + chaptersText;
    }

    /**
     * Transition UI to the result state with the given status and message.
     * @param {'success'|'error'} status
     * @param {string} message
     */
    function showResult(status, message) {
        stopPolling();
        loading.classList.add('hidden');
        if (preview) { preview.classList.add('hidden'); }
        if (progress) { progress.classList.add('hidden'); }
        resultMessage.textContent = message;
        resultMessage.className = status;
        result.classList.remove('hidden');
    }

    /**
     * Poll GET /api/progress/<task_id> every second until done or error.
     * @param {string} taskId
     */
    function pollProgress(taskId) {
        stopPolling();
        pollStartTime = Date.now();

        pollTimer = setInterval(function () {
            fetch('/api/progress/' + taskId)
                .then(function (response) {
                    if (!response.ok) {
                        // 404: task not found (cleanup, different worker, crash, etc.)
                        var elapsed = (Date.now() - pollStartTime) / 1000;
                        if (elapsed > 15) {
                            // We've been polling for a while — task likely expired
                            stopPolling();
                            showResult('error',
                                'Download status unavailable. The task may have expired. ' +
                                'Check the data folder — the download may still have completed.'
                            );
                        }
                        // If we haven't been polling long, ignore transient 404s
                        return null;
                    }
                    return response.json();
                })
                .then(function (data) {
                    if (!data) { return; }

                    if (data.status === 'done') {
                        stopPolling();
                        if (progress) { progress.classList.add('hidden'); }
                        showResult('success', data.message || 'Download complete.');
                    } else if (data.status === 'error') {
                        stopPolling();
                        if (progress) { progress.classList.add('hidden'); }
                        showResult('error', 'Download failed: ' + (data.message || 'Unknown error'));
                    } else if (data.status === 'downloading' || data.status === 'starting') {
                        updateProgress(data);
                    }
                })
                .catch(function (err) {
                    // Network flakiness — keep polling, the interval will retry
                    console.error('Progress poll error:', err);
                });
        }, 1000);
    }

    /**
     * Reset the UI back to the initial form state.
     */
    function resetUI() {
        stopPolling();
        comicIdInput.value = '';
        submitButton.disabled = false;
        if (previewButton) { previewButton.disabled = false; }
        result.classList.add('hidden');
        if (preview) { preview.classList.add('hidden'); }
        if (progress) { progress.classList.add('hidden'); }
        form.classList.remove('hidden');
        comicIdInput.focus();
    }

    /**
     * Populate and show the preview card with album metadata.
     * @param {object} data — API response data
     */
    function showPreview(data) {
        loading.classList.add('hidden');

        // Cover image
        previewCover.src = data.cover_url || '';
        previewCover.alt = 'Cover for ' + (data.title || data.album_id);

        // Title
        previewTitleEl.textContent = data.title || data.album_id;

        // Authors
        if (data.authors && data.authors.length) {
            previewAuthors.textContent = 'By ' + data.authors.join(', ');
        } else {
            previewAuthors.textContent = '';
        }

        // Tags
        previewTags.innerHTML = '';
        if (data.tags && data.tags.length) {
            data.tags.forEach(function (tag) {
                var pill = document.createElement('span');
                pill.className = 'tag-pill';
                pill.textContent = tag;
                previewTags.appendChild(pill);
            });
        }

        // Description (truncated)
        if (data.description) {
            previewDescription.textContent = data.description.length > 300
                ? data.description.slice(0, 300) + '…'
                : data.description;
            previewDescription.classList.remove('hidden');
        } else {
            previewDescription.classList.add('hidden');
        }

        // Stats
        previewViews.textContent = data.views ? '👁 ' + Number(data.views).toLocaleString() : '';
        previewLikes.textContent = data.likes ? '❤️ ' + Number(data.likes).toLocaleString() : '';
        previewPages.textContent = data.page_count ? '📄 ' + data.page_count + ' pages' : '';
        previewChapters.textContent = data.chapter_count ? '📁 ' + data.chapter_count + ' chapters' : '';

        preview.classList.remove('hidden');
    }

    /**
     * Start a download (background task + progress polling).
     * @param {string} comicId
     */
    function startDownload(comicId) {
        showLoading('Starting download…');

        fetch('/api/download', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ comic_id: comicId })
        })
            .then(function (response) {
                return response.json().then(function (data) {
                    return { ok: response.ok, data: data };
                });
            })
            .then(function (result) {
                if (result.data.status === 'accepted') {
                    showProgressView();
                    pollProgress(result.data.task_id);
                } else {
                    showResult('error', result.data.message || 'Failed to start download');
                }
            })
            .catch(function (err) {
                showResult('error', 'Network error — please check your connection and try again.');
                console.error(err);
            });
    }

    // --- Event Listeners ---

    // Form submission (Download button in the main form)
    form.addEventListener('submit', function (e) {
        e.preventDefault();
        var comicId = comicIdInput.value.trim();
        if (!comicId) { return; }
        startDownload(comicId);
    });

    // Preview button
    if (previewButton && preview) {
        previewButton.addEventListener('click', function () {
            var comicId = comicIdInput.value.trim();
            if (!comicId) { return; }

            showLoading('Fetching album info…');

            fetch('/api/preview', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ comic_id: comicId })
            })
                .then(function (response) {
                    return response.json().then(function (data) {
                        return { ok: response.ok, data: data };
                    });
                })
                .then(function (result) {
                    if (result.data.status === 'success') {
                        showPreview(result.data);
                    } else {
                        showResult('error', 'Preview failed: ' + (result.data.message || 'Unknown error'));
                    }
                })
                .catch(function (err) {
                    showResult('error', 'Network error — please check your connection and try again.');
                    console.error(err);
                });
        });
    }

    // "Download" button inside the preview card
    if (previewDownloadBtn) {
        previewDownloadBtn.addEventListener('click', function () {
            var comicId = comicIdInput.value.trim();
            if (!comicId) { return; }
            startDownload(comicId);
        });
    }

    // "Cancel" button inside the preview card
    if (previewCancelBtn) {
        previewCancelBtn.addEventListener('click', resetUI);
    }

    // "Download Another" button in result view
    resetButton.addEventListener('click', resetUI);

})();
