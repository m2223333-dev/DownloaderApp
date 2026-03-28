# Futuristic Video Downloader Implementation Plan

This project will build a modern, high-performance video downloader web app featuring a Flask backend and a vanilla HTML/CSS/JS frontend with a stunning, futuristic (Antigravity-style) user interface.

## User Review Required

> [!IMPORTANT]  
> Please review the chosen dependencies and the overall architecture. Since this is a lightweight application, I've opted for vanilla HTML/CSS/JS on the frontend to maximize performance and avoid the overhead of heavy frameworks, fulfilling your request for a clean structure. The backend uses Python, Flask, and yt-dlp.

## Proposed Changes

### Backend (Flask API)

#### [NEW] `app.py`
The core Flask application exposing the API.
*   **Endpoint `/extract`**: Accepts a JSON `POST` request with a video URL.
*   **yt-dlp Integration**: Uses `YoutubeDL` in extraction-only mode (`skip_download=True`).
*   **Format Filtering**: Iterates through the extracted formats and returns only "progressive" formats (where both audio and video streams exist together without requiring merging, i.e., `vcodec != 'none'` and `acodec != 'none'`).
*   **Anti-Detection**: Configures `yt-dlp` to use realistic user-agent strings.
*   **Rate Limiting**: Implements a simple in-memory IP-based rate limiting dictionary to prevent rapid repeated requests.

#### [NEW] `requirements.txt`
Dependencies list: `Flask`, `yt-dlp`, `flask-cors`.

### Frontend (Static Files & Templates)

#### [NEW] `templates/index.html`
The main visual structure of the application.
*   **Layout**: Centered hero section containing input, extraction results, and a premium "Desktop App" promotion card.
*   **Structure**: Semantic HTML with clear ID tags for DOM manipulation.
*   **Assets**: Links to Google Fonts (Inter/Outfit for modern typography).

#### [NEW] `static/css/style.css`
The core design system and styling.
*   **Theme**: Deep black and dark gradients with neon blue, electric purple, cyan glow, and soft pink highlights.
*   **Glassmorphism**: Translucent cards with subtle white borders and background blurring (`backdrop-filter: blur()`).
*   **Animations**: Continuous background gradient animation, futuristic pulsing loading spinner, button hover glow effects, input focus states, and a smooth initial page load animation.
*   **Responsive**: Breakpoints for mobile, tablet, and desktop viewing.

#### [NEW] `static/js/main.js`
The application logic.
*   **Event Listeners**: Handles the form submission (URL extraction), copy link, and clear input buttons.
*   **API Calls**: Uses `fetch()` to call the `/extract` backend endpoint asynchronously.
*   **UX Features**: Adds an artificial 0.5 - 1.0 second delay for smooth transition effects. Handles errors gracefully (e.g., displaying error status when the URL is invalid).
*   **Download Logic**: Binds the extracted progressive formats to buttons that perform `window.open(url, '_blank')`, leaving the actual downloading to the user's browser.

## Open Questions

> [!TIP]  
> 1.  Do you have an existing Desktop App link (or placeholder) you'd like me to use for the "Download Desktop App" premium card? If not, I'll use a placeholder `#`.
> 2.  Are there specific fonts you prefer? I plan to use `Outfit` or `Inter` from Google Fonts to give it a sleek, modern look.

## Verification Plan

### Automated/Manual Testing
*   Start the Flask development server using `python app.py`.
*   Open the application in a browser and verify the initial loading animation and responsive layout.
*   Test extraction using a sample YouTube video URL.
*   Verify the loading spinner appears, an artificial delay occurs, and the result displays a thumbnail, title, and buttons for progressive formats only.
*   Ensure clicking a format button opens the video URL directly in a new tab.
*   Test invalid generic URLs to ensure error messages are properly displayed.
*   Test rapid requests to verify the simple rate limiter blocks them.
