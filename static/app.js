(function () {
    'use strict';

    var form = document.getElementById('submissionForm');
    var loading = document.getElementById('loading');
    var result = document.getElementById('result');
    var resultMessage = document.getElementById('resultMessage');
    var resetButton = document.getElementById('resetButton');
    var submitButton = document.getElementById('submitButton');
    var comicIdInput = document.getElementById('comicId');

    // If any required element is missing, bail out (graceful degradation)
    if (!form || !loading || !result || !resetButton || !submitButton || !comicIdInput) {
        return;
    }

    /**
     * Transition UI to the loading state.
     */
    function showLoading() {
        form.classList.add('hidden');
        result.classList.add('hidden');
        loading.classList.remove('hidden');
        submitButton.disabled = true;
    }

    /**
     * Transition UI to the result state with the given status and message.
     * @param {'success'|'error'} status
     * @param {string} message
     */
    function showResult(status, message) {
        loading.classList.add('hidden');
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
        result.classList.add('hidden');
        form.classList.remove('hidden');
        comicIdInput.focus();
    }

    // Intercept form submission for async handling
    form.addEventListener('submit', function (e) {
        e.preventDefault();

        var comicId = comicIdInput.value.trim();
        if (!comicId) {
            return;
        }

        showLoading();

        fetch('/api/download', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ comic_id: comicId })
        })
            .then(function (response) {
                // Parse JSON regardless of status code — our API always returns JSON
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
                // Network-level error (fetch itself failed)
                showResult('error', 'Network error — please check your connection and try again.');
                console.error(err);
            });
    });

    // "Download Another" button returns to the form
    resetButton.addEventListener('click', resetUI);

})();
