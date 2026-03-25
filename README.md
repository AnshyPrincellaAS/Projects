# Projects

## Spotify Mood Guardian

This repo now includes `spotify_mood_guardian.py`, a Python program for:
- Spotify-based mood analysis from recently played tracks.
- Dark-trend detection (alerts when listening pattern gets consistently heavy).
- Smart song recommendations for a selected target mood (`uplift`, `calm`, `focus`, `hype`).

### Quick start

```bash
pip install spotipy
export SPOTIPY_CLIENT_ID="..."
export SPOTIPY_CLIENT_SECRET="..."
export SPOTIPY_REDIRECT_URI="http://localhost:8080/callback"
python spotify_mood_guardian.py --limit 40 --target-mood uplift
```

### Dark-alert tuning

```bash
python spotify_mood_guardian.py --dark-threshold 55 --dark-streak-trigger 6
```
