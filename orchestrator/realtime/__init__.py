"""Inworld full-loop realtime runtime (Track V).

Drives one Inworld Realtime session (STT -> Claude -> Realtime TTS-2, with cross-turn
voice continuity) as an alternative to the modular `pipeline.Pipeline`. Selected by
`settings.voice_runtime == "inworld_fullloop"`. See docs/track-v-full-loop-plan.md.
"""
