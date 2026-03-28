document.addEventListener('DOMContentLoaded', () => {
    // UI Elements
    const overlay = document.getElementById('initial-overlay');
    const urlInput = document.getElementById('video-url');
    const clearBtn = document.getElementById('clear-btn');
    const extractBtn = document.getElementById('extract-btn');
    const errorMsg = document.getElementById('error-message');
    const errorText = document.getElementById('error-text');
    const loader = document.getElementById('extraction-loader');
    const resultsContainer = document.getElementById('results-container');
    const copyLinkBtn = document.getElementById('copy-link-btn');
    
    // Result Elements
    const thumbImg = document.getElementById('thumb-img');
    const videoTitle = document.getElementById('video-title');
    const formatDropdown = document.getElementById('format-dropdown');
    const masterDownloadBtn = document.getElementById('master-download-btn');

    // 1. Initial Load Animation
    // Hide overlay after a slight delay for dramatic effect
    setTimeout(() => {
        overlay.classList.add('fade-out');
        setTimeout(() => overlay.style.display = 'none', 600);
    }, 1500);

    // 2. Input Interactions
    urlInput.addEventListener('input', () => {
        if (urlInput.value.trim() !== '') {
            clearBtn.style.display = 'block';
        } else {
            clearBtn.style.display = 'none';
        }
        hideError();
    });

    clearBtn.addEventListener('click', () => {
        urlInput.value = '';
        clearBtn.style.display = 'none';
        urlInput.focus();
        hideError();
    });

    urlInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            extractVideo();
        }
    });

    // 3. Extract Button Logic
    extractBtn.addEventListener('click', extractVideo);

    async function extractVideo() {

        const url = urlInput.value.trim();
        
        if (!url) {
            showError('Please enter a valid video URL.');
            return;
        }

        // Regex for basic URL validation
        const urlPattern = /^(https?:\/\/)?([\w.-]+)\.([a-z]{2,})(:\d{1,5})?(\/.*)?$/i;
        if (!urlPattern.test(url)) {
            showError('Invalid URL format. Please try again.');
            return;
        }

        // Prepare UI for loading
        hideError();
        resultsContainer.classList.add('hidden');
        loader.classList.remove('hidden');
        extractBtn.disabled = true;
        extractBtn.style.opacity = '0.7';

        try {
            // Fetch data from backend
            const response = await fetch('/extract', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ url: url })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Extraction failed. Server returned an error.');
            }

            renderResults(data, url);

        } catch (error) {
            console.error('Error:', error);
            showError(error.message);
        } finally {
            loader.classList.add('hidden');
            extractBtn.disabled = false;
            extractBtn.style.opacity = '1';
        }
    }

    // 4. Render Results
    function renderResults(data, originalUrl) {
        // Set basic info
        videoTitle.textContent = data.title;
        thumbImg.src = data.thumbnail || 'https://via.placeholder.com/640x360.png?text=No+Thumbnail';

        // Set formats dropdown
        formatDropdown.innerHTML = '<option value="">-- Select Quality & Format --</option>';
        masterDownloadBtn.classList.add('disabled-btn');
        masterDownloadBtn.href = "#";
        
        if (data.formats && data.formats.length > 0) {

            // Detect if backend auto-unlocked the lowest format
            // (all others will still be premium; exactly one will not be)
            const premiumCount = data.formats.filter(f => f.is_premium).length;
            const autoUnlocked = (premiumCount === data.formats.length - 1) &&
                                 !data.formats[data.formats.length - 1].is_premium &&
                                 data.formats.length > 1;

            data.formats.forEach((f, idx) => {
                const opt = document.createElement('option');
                opt.value = idx;
                
                let sizeStr = f.filesize ? `${(f.filesize / (1024 * 1024)).toFixed(1)} MB` : 'Unknown Size';
                let mergeTag = f.is_progressive ? "(Instant)" : "(Server Merge)";
                
                if (f.is_premium) {
                    opt.textContent = `🔒 ${f.resolution} - ${f.ext} (App Required)`;
                    opt.disabled = true;
                } else if (autoUnlocked && idx === data.formats.length - 1) {
                    opt.textContent = `🔓 ${f.resolution} - ${f.ext} ${mergeTag} · Auto-unlocked`;
                } else {
                    opt.textContent = `${f.resolution} - ${f.ext} ${mergeTag}`;
                }
                formatDropdown.appendChild(opt);
            });

            formatDropdown.dataset.formats = JSON.stringify(data.formats);
            
            // Listen for selection changes natively using onchange to prevent duplicate handlers
            formatDropdown.onchange = () => {
                const selectedIdx = formatDropdown.value;
                if (selectedIdx === "") {
                    masterDownloadBtn.classList.add('disabled-btn');
                    masterDownloadBtn.innerHTML = '<i class="ph ph-download-simple"></i> Download Selected';
                } else {
                    masterDownloadBtn.classList.remove('disabled-btn');
                    // Premium items handle button override logic just in case an expert forcibly bypasses 'disabled' in the DOM.
                    const selectedFormat = JSON.parse(formatDropdown.dataset.formats)[selectedIdx];
                    if (selectedFormat.is_premium) {
                        masterDownloadBtn.innerHTML = '<i class="ph ph-crown glow-cyan"></i> Get App For 4K';
                    } else {
                        masterDownloadBtn.innerHTML = '<i class="ph ph-download-simple"></i> Download Selected';
                    }
                }
            };

            // Dynamic logic when user clicks the Download button!
            masterDownloadBtn.onclick = (e) => {
                const selectedIdx = formatDropdown.value;
                if (selectedIdx === "") {
                    e.preventDefault();
                    return;
                }
                
                const selectedFormat = JSON.parse(formatDropdown.dataset.formats)[selectedIdx];
                
                if (selectedFormat.is_premium) {
                    e.preventDefault();
                    alert("To download stunning 4K and 8K videos without limits, please install our official Desktop Application.");
                    // In the future: window.location.href = "your_app.exe";
                    return;
                }
                
                if (selectedFormat.is_progressive) {
                    // FAST Route: Instant Direct Proxy Stream
                    masterDownloadBtn.href = `/proxy?url=${encodeURIComponent(selectedFormat.url)}&title=${encodeURIComponent(data.title)}&ext=${selectedFormat.ext}`;
                    masterDownloadBtn.download = `video.${selectedFormat.ext}`; // Let native routing trigger download directly!
                } else {
                    // SLOW Route: High-Res FFmpeg Merge Pipeline
                    e.preventDefault(); // Stop normal click
                    
                    const originalText = masterDownloadBtn.innerHTML;
                    masterDownloadBtn.classList.add('disabled-btn');
                    masterDownloadBtn.innerHTML = `<i class="ph ph-spinner ph-spin"></i> Initializing Download...`;
                    
                    // Ping background API
                    fetch('/api/start_merge', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            url: originalUrl,
                            format_id: selectedFormat.format_id,
                            title: data.title
                        })
                    })
                    .then(r => r.json())
                    .then(res => {
                        if (res.error) throw new Error(res.error);
                        
                        const jobId = res.job_id;
                        
                        // Begin 1-second interval polling
                        const poll = setInterval(() => {
                            fetch(`/api/progress/${jobId}`)
                            .then(pr => pr.json())
                            .then(p => {
                                if (p.error) throw new Error(p.error);
                                
                                if (p.status === 'downloading') {
                                    masterDownloadBtn.innerHTML = `<i class="ph ph-spinner ph-spin"></i> Downloading: ${p.percent} (ETA: ${p.eta})`;
                                } else if (p.status === 'merging') {
                                    masterDownloadBtn.innerHTML = `<i class="ph ph-arrows-merge ph-spin"></i> Stitching AV Layers...`;
                                } else if (p.status === 'finished') {
                                    clearInterval(poll);
                                    masterDownloadBtn.innerHTML = `<i class="ph ph-check-circle"></i> Success! Initiating Transfer...`;
                                    
                                    // Trigger browser download popup
                                    window.location.href = `/api/get_file/${jobId}`;
                                    
                                    // Reset perfectly after 5 seconds
                                    setTimeout(() => {
                                        masterDownloadBtn.innerHTML = originalText;
                                        masterDownloadBtn.classList.remove('disabled-btn');
                                    }, 5000);
                                } else if (p.status === 'error') {
                                    throw new Error(p.message || 'Unknown Server Error');
                                }
                            })
                            .catch(err => {
                                clearInterval(poll);
                                alert("Sync Error: " + err.message);
                                masterDownloadBtn.innerHTML = originalText;
                                masterDownloadBtn.classList.remove('disabled-btn');
                            });
                        }, 1000);
                    })
                    .catch(err => {
                        alert("Start Error: " + err.message);
                        masterDownloadBtn.innerHTML = originalText;
                        masterDownloadBtn.classList.remove('disabled-btn');
                    });
                }
            };

        } else {
            formatDropdown.innerHTML = '<option value="">No extractable formats found.</option>';
        }

        // Show results
        resultsContainer.classList.remove('hidden');
    }

    // 5. Utilities
    function showError(message) {
        errorText.textContent = message;
        errorMsg.classList.remove('hidden');
        resultsContainer.classList.add('hidden');
    }

    function hideError() {
        errorMsg.classList.add('hidden');
    }

    copyLinkBtn.addEventListener('click', () => {
        const url = urlInput.value.trim();
        if (url) {
            navigator.clipboard.writeText(url).then(() => {
                const originalText = copyLinkBtn.innerHTML;
                copyLinkBtn.innerHTML = '<i class="ph ph-check"></i> Copied!';
                copyLinkBtn.style.color = 'var(--primary-blue)';
                setTimeout(() => {
                    copyLinkBtn.innerHTML = originalText;
                    copyLinkBtn.style.color = '';
                }, 2000);
            });
        }
    });
});
