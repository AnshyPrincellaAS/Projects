#!/usr/bin/env python3
"""
Spotify Smart Recommendation + Mood Detection + Dark Trend Alert

What this script does:
1. Reads your recently played Spotify tracks.
2. Pulls audio features for each song.
3. Estimates mood of each song and your overall listening trend.
4. Alerts you if your recent choices look "dark" for a sustained window.
5. Suggests songs aligned with a target mood.

Setup:
- Create a Spotify app: https://developer.spotify.com/dashboard
- Export env vars:
  export SPOTIPY_CLIENT_ID="..."
  export SPOTIPY_CLIENT_SECRET="..."
  export SPOTIPY_REDIRECT_URI="http://localhost:8080/callback"

Install:
  pip install spotipy

Run examples:
  python spotify_mood_guardian.py --limit 40 --target-mood uplift
  python spotify_mood_guardian.py --target-mood calm --dark-threshold 35
"""

from __future__ import annotations

import argparse
import statistics
from dataclasses import dataclass
from typing import Dict, List, Optional

import spotipy
from spotipy.oauth2 import SpotifyOAuth

SCOPES = "user-read-recently-played"


@dataclass
class TrackMood:
    track_id: str
    name: str
    artists: str
    valence: float
    energy: float
    danceability: float
    acousticness: float
    tempo: float
    key: int
    mode: int
    mood_score: float
    dark_score: float
    label: str


def auth_spotify() -> spotipy.Spotify:
    return spotipy.Spotify(
        auth_manager=SpotifyOAuth(
            scope=SCOPES,
            open_browser=True,
            cache_path=".spotify_mood_guardian.cache",
        )
    )


def chunked(items: List[str], size: int = 100):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def classify_mood(valence: float, energy: float, danceability: float, acousticness: float) -> str:
    if valence >= 0.65 and energy >= 0.6:
        return "happy"
    if energy >= 0.7 and danceability >= 0.65:
        return "hyped"
    if valence < 0.4 and energy < 0.5 and acousticness > 0.45:
        return "melancholic"
    if energy < 0.45 and acousticness >= 0.4:
        return "calm"
    return "balanced"


def compute_scores(features: Dict) -> Dict[str, float]:
    valence = features.get("valence") or 0.0
    energy = features.get("energy") or 0.0
    danceability = features.get("danceability") or 0.0
    acousticness = features.get("acousticness") or 0.0
    mode = features.get("mode") or 0

    # mood_score: higher means brighter/uplifting
    mood_score = (
        valence * 55
        + energy * 20
        + danceability * 15
        + (1 - acousticness) * 5
        + (5 if mode == 1 else 0)
    )

    # dark_score: higher means darker/sadder pattern
    dark_score = (
        (1 - valence) * 55
        + (1 - energy) * 12
        + acousticness * 18
        + (8 if mode == 0 else 0)
        + (7 if (valence < 0.35 and energy < 0.45) else 0)
    )

    return {"mood_score": mood_score, "dark_score": dark_score}


def get_recent_track_moods(sp: spotipy.Spotify, limit: int) -> List[TrackMood]:
    recent = sp.current_user_recently_played(limit=limit)
    items = recent.get("items", [])
    track_ids: List[str] = []

    for item in items:
        t = item.get("track", {})
        tid = t.get("id")
        if tid:
            track_ids.append(tid)

    if not track_ids:
        return []

    feature_map: Dict[str, Dict] = {}
    for ids in chunked(track_ids, size=100):
        feats = sp.audio_features(ids)
        for feature in feats:
            if feature and feature.get("id"):
                feature_map[feature["id"]] = feature

    rows: List[TrackMood] = []
    for item in items:
        track = item.get("track", {})
        tid = track.get("id")
        if not tid or tid not in feature_map:
            continue

        feat = feature_map[tid]
        scores = compute_scores(feat)
        artists = ", ".join(a.get("name", "") for a in track.get("artists", []))
        label = classify_mood(
            valence=feat.get("valence", 0.0),
            energy=feat.get("energy", 0.0),
            danceability=feat.get("danceability", 0.0),
            acousticness=feat.get("acousticness", 0.0),
        )

        rows.append(
            TrackMood(
                track_id=tid,
                name=track.get("name", "Unknown"),
                artists=artists,
                valence=feat.get("valence", 0.0),
                energy=feat.get("energy", 0.0),
                danceability=feat.get("danceability", 0.0),
                acousticness=feat.get("acousticness", 0.0),
                tempo=feat.get("tempo", 0.0),
                key=feat.get("key", 0),
                mode=feat.get("mode", 0),
                mood_score=scores["mood_score"],
                dark_score=scores["dark_score"],
                label=label,
            )
        )

    return rows


def summarize_mood(rows: List[TrackMood]) -> Dict[str, float | str]:
    if not rows:
        return {
            "avg_mood": 0.0,
            "avg_dark": 0.0,
            "dominant": "unknown",
            "dark_streak": 0,
        }

    avg_mood = statistics.mean(r.mood_score for r in rows)
    avg_dark = statistics.mean(r.dark_score for r in rows)

    labels: Dict[str, int] = {}
    for r in rows:
        labels[r.label] = labels.get(r.label, 0) + 1

    dominant = max(labels.items(), key=lambda x: x[1])[0]

    dark_streak = 0
    for r in rows:
        if r.dark_score >= 60:
            dark_streak += 1
        else:
            break

    return {
        "avg_mood": round(avg_mood, 2),
        "avg_dark": round(avg_dark, 2),
        "dominant": dominant,
        "dark_streak": dark_streak,
    }


def dark_alert(summary: Dict[str, float | str], threshold: float, streak_trigger: int) -> Optional[str]:
    avg_dark = float(summary["avg_dark"])
    dark_streak = int(summary["dark_streak"])

    if avg_dark >= threshold or dark_streak >= streak_trigger:
        return (
            "⚠️ DARK TREND ALERT: Your recent listening pattern looks heavy. "
            "Consider a mood reset playlist, a short walk, or check in with a friend."
        )
    return None


def recommendation_targets(target_mood: str) -> Dict[str, float]:
    profiles = {
        "uplift": {"valence": 0.8, "energy": 0.72, "danceability": 0.72, "acousticness": 0.2},
        "calm": {"valence": 0.62, "energy": 0.38, "danceability": 0.5, "acousticness": 0.68},
        "focus": {"valence": 0.56, "energy": 0.45, "danceability": 0.45, "acousticness": 0.52},
        "hype": {"valence": 0.7, "energy": 0.88, "danceability": 0.8, "acousticness": 0.12},
    }
    return profiles.get(target_mood, profiles["uplift"])


def get_seed_tracks(rows: List[TrackMood], count: int = 5) -> List[str]:
    # Prefer recent tracks with better mood scores as recommendation anchors.
    ranked = sorted(rows, key=lambda x: x.mood_score, reverse=True)
    return [r.track_id for r in ranked[:count]]


def recommend_songs(sp: spotipy.Spotify, rows: List[TrackMood], target_mood: str, limit: int = 10):
    if not rows:
        return []

    seeds = get_seed_tracks(rows)
    targets = recommendation_targets(target_mood)

    recs = sp.recommendations(
        seed_tracks=seeds,
        limit=limit,
        target_valence=targets["valence"],
        target_energy=targets["energy"],
        target_danceability=targets["danceability"],
        target_acousticness=targets["acousticness"],
    )
    return recs.get("tracks", [])


def parse_args():
    parser = argparse.ArgumentParser(description="Smart Spotify mood detection and recommendation tool")
    parser.add_argument("--limit", type=int, default=40, help="Number of recent songs to inspect")
    parser.add_argument(
        "--target-mood",
        type=str,
        default="uplift",
        choices=["uplift", "calm", "focus", "hype"],
        help="Mood profile for recommendations",
    )
    parser.add_argument(
        "--dark-threshold",
        type=float,
        default=55.0,
        help="Average dark score threshold for triggering alert",
    )
    parser.add_argument(
        "--dark-streak-trigger",
        type=int,
        default=6,
        help="Consecutive dark songs from most recent side to trigger alert",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    sp = auth_spotify()

    moods = get_recent_track_moods(sp, limit=args.limit)
    if not moods:
        print("No recent tracks found. Play some music and run again.")
        return

    summary = summarize_mood(moods)
    alert = dark_alert(summary, args.dark_threshold, args.dark_streak_trigger)

    print("\n=== Mood Summary ===")
    print(f"Tracks analyzed : {len(moods)}")
    print(f"Average mood    : {summary['avg_mood']} / 100")
    print(f"Average dark    : {summary['avg_dark']} / 100")
    print(f"Dominant vibe   : {summary['dominant']}")
    print(f"Dark streak     : {summary['dark_streak']} tracks")

    if alert:
        print(f"\n{alert}")
    else:
        print("\n✅ No sustained dark trend detected.")

    print("\n=== Latest 5 Song Mood Labels ===")
    for row in moods[:5]:
        print(f"- {row.name} — {row.artists} | {row.label} (dark={row.dark_score:.1f})")

    recommendations = recommend_songs(sp, moods, target_mood=args.target_mood, limit=10)
    print(f"\n=== Smart Recommendations ({args.target_mood}) ===")
    for idx, track in enumerate(recommendations, start=1):
        artists = ", ".join(a["name"] for a in track.get("artists", []))
        print(f"{idx:02d}. {track.get('name', 'Unknown')} — {artists}")


if __name__ == "__main__":
    main()
