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
    var previewTitle = document.getElementById('previewTitle');
    var previewAuthors = document.getElementById('previewAuthors');
    var previewTags = document.getElementById('previewTags');
    var previewDescription = document.getElementById('previewDescription');
    var previewViews = document.getElementById('previewViews');
    var previewLikes = document.getElementById('previewLikes');
    var previewPages = document.getElementById('previewPages');
    var previewChapters = document.getElementById('previewChapters');
    var previewDownloadBtn = document.getElementById('previewDownloadButton');
    var previewCancelBtn = document.getElementById('previewCancelButton');

    // If any required element is missing, bail out (graceful degradation)
    if (!form || !loading || !result || !resetButton || !submitButton || !comicIdInput) {
        return;
    }

    /**
     * Transition UI to the loading state.
     * @param {string} [message='Loading, please wait…']
     */
    function showLoading(message) {
        form.classList.add('hidden');
        result.classList.add('hidden');
        if (preview) { preview.classList.add('hidden'); }
        loadingText.textContent = message || 'Loading, please wait…';
        loading.classList.remove('hidden');
        submitButton.disabled = true;
        if (previewButton) { previewButton.disabled = true; }
    }

    /**
     * Transition UI to the result state with the given status and message.
     * @param {'success'|'error'} status
     * @param {string} message
     */
    function showResult(status, message) {
        loading.classList.add('hidden');
        if (preview) { preview.classList.add('hidden'); }
        resultMessage.textContent = message;
        resultMessage.className = status;
        result.classList.remove('hidden');
    }

    /**
     * Reset the UI back to the initial form state.
     */
    function resetUI() {
        comicIdInput.value = '';
        submitButton.disabled = false;
        if (previewButton) { previewButton.disabled = false; }
        result.classList.add('hidden');
        if (preview) { preview.classList.add('hidden'); }
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
        previewTitle.textContent = data.title || data.album_id;

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
     * Start the download for the given comic ID.
     * @param {string} comicId
     */
    function startDownload(comicId) {
        showLoading('Downloading, please wait…');

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
                if (result.data.status === 'success') {
                    showResult('success', result.data.message);
                } else {
                    showResult('error', 'Download failed: ' + (result.data.message || 'Unknown error'));
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
