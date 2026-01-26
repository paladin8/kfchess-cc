/**
 * Audio Hook - Manages game audio playback
 *
 * Handles background music and sound effects with volume controls.
 * Volume settings are persisted to localStorage.
 */

import { useEffect, useRef, useCallback, useState } from 'react';
import { staticUrl } from '../config';

// Audio file paths
const MUSIC_PATH = staticUrl('audio/kfchess-music.mp3');
const GONG_PATH = staticUrl('audio/kfchess-gong.mp3');
const CAPTURE_SOUNDS = [
  staticUrl('audio/kfchess-sound1.mp3'),
  staticUrl('audio/kfchess-sound2.mp3'),
  staticUrl('audio/kfchess-sound3.mp3'),
  staticUrl('audio/kfchess-sound4.mp3'),
  staticUrl('audio/kfchess-sound5.mp3'),
  staticUrl('audio/kfchess-sound6.mp3'),
  staticUrl('audio/kfchess-sound7.mp3'),
  staticUrl('audio/kfchess-sound8.mp3'),
];

// localStorage keys
const MUSIC_VOLUME_KEY = 'musicVolume';
const SOUND_VOLUME_KEY = 'soundVolume';

// Default volume (0-100)
const DEFAULT_VOLUME = 20;

function getStoredVolume(key: string): number {
  if (typeof window === 'undefined' || !window.localStorage) {
    return 0; // No localStorage, default to muted
  }
  const stored = localStorage.getItem(key);
  if (stored !== null) {
    const parsed = parseInt(stored, 10);
    if (!isNaN(parsed) && parsed >= 0 && parsed <= 100) {
      return parsed;
    }
  }
  return DEFAULT_VOLUME;
}

function setStoredVolume(key: string, value: number): void {
  if (typeof window !== 'undefined' && window.localStorage) {
    localStorage.setItem(key, String(value));
  }
}

export interface UseAudioOptions {
  /** Whether the game is currently playing (for background music) */
  isPlaying: boolean;
  /** Whether the game is finished (for gong sound) */
  isFinished: boolean;
}

export interface UseAudioResult {
  /** Current music volume (0-100) */
  musicVolume: number;
  /** Current sound effects volume (0-100) */
  soundVolume: number;
  /** Set music volume (0-100) */
  setMusicVolume: (volume: number) => void;
  /** Set sound effects volume (0-100) */
  setSoundVolume: (volume: number) => void;
  /** Play a random capture sound */
  playCaptureSound: () => void;
}

export function useAudio({ isPlaying, isFinished }: UseAudioOptions): UseAudioResult {
  // Volume state
  const [musicVolume, setMusicVolumeState] = useState(() => getStoredVolume(MUSIC_VOLUME_KEY));
  const [soundVolume, setSoundVolumeState] = useState(() => getStoredVolume(SOUND_VOLUME_KEY));

  // Audio element refs
  const musicRef = useRef<HTMLAudioElement | null>(null);
  const gongRef = useRef<HTMLAudioElement | null>(null);
  const captureSoundsRef = useRef<HTMLAudioElement[]>([]);

  // Track previous states to detect transitions
  const wasPlayingRef = useRef(false);
  const wasFinishedRef = useRef(false);

  // Initialize audio elements on mount
  useEffect(() => {
    // Create music element
    const music = new Audio(MUSIC_PATH);
    music.loop = true;
    music.volume = musicVolume / 100;
    musicRef.current = music;

    // Create gong element
    const gong = new Audio(GONG_PATH);
    gong.volume = soundVolume / 100;
    gongRef.current = gong;

    // Create capture sound elements
    captureSoundsRef.current = CAPTURE_SOUNDS.map((path) => {
      const audio = new Audio(path);
      audio.volume = soundVolume / 100;
      return audio;
    });

    // Cleanup on unmount
    return () => {
      music.pause();
      music.src = '';
      gong.src = '';
      captureSoundsRef.current.forEach((audio) => {
        audio.src = '';
      });
      musicRef.current = null;
      gongRef.current = null;
      captureSoundsRef.current = [];
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Only run on mount

  // Update music volume
  useEffect(() => {
    if (musicRef.current) {
      musicRef.current.volume = musicVolume / 100;
    }
  }, [musicVolume]);

  // Update sound effects volume
  useEffect(() => {
    if (gongRef.current) {
      gongRef.current.volume = soundVolume / 100;
    }
    captureSoundsRef.current.forEach((audio) => {
      audio.volume = soundVolume / 100;
    });
  }, [soundVolume]);

  // Handle music playback based on game state
  useEffect(() => {
    const music = musicRef.current;
    if (!music) return;

    if (isPlaying && !isFinished) {
      // Game is active - play music
      // Use a user interaction check - browsers block autoplay without interaction
      const playPromise = music.play();
      if (playPromise !== undefined) {
        playPromise.catch(() => {
          // Autoplay was prevented - this is normal, music will start on user interaction
        });
      }
    } else {
      // Game not active - pause and reset
      music.pause();
      music.currentTime = 0;
    }

    wasPlayingRef.current = isPlaying;
  }, [isPlaying, isFinished]);

  // Handle game over gong sound
  useEffect(() => {
    // Only play gong on transition to finished state
    if (isFinished && !wasFinishedRef.current) {
      const gong = gongRef.current;
      if (gong && soundVolume > 0) {
        gong.currentTime = 0;
        gong.play().catch(() => {
          // Autoplay blocked - ignore
        });
      }
    }
    wasFinishedRef.current = isFinished;
  }, [isFinished, soundVolume]);

  // Volume setters with persistence
  const setMusicVolume = useCallback((volume: number) => {
    const clamped = Math.max(0, Math.min(100, volume));
    setMusicVolumeState(clamped);
    setStoredVolume(MUSIC_VOLUME_KEY, clamped);
  }, []);

  const setSoundVolume = useCallback((volume: number) => {
    const clamped = Math.max(0, Math.min(100, volume));
    setSoundVolumeState(clamped);
    setStoredVolume(SOUND_VOLUME_KEY, clamped);
  }, []);

  // Play random capture sound
  const playCaptureSound = useCallback(() => {
    if (soundVolume === 0) return;

    const sounds = captureSoundsRef.current;
    if (sounds.length === 0) return;

    const randomIndex = Math.floor(Math.random() * sounds.length);
    const sound = sounds[randomIndex];
    sound.currentTime = 0;
    sound.play().catch(() => {
      // Autoplay blocked - ignore
    });
  }, [soundVolume]);

  return {
    musicVolume,
    soundVolume,
    setMusicVolume,
    setSoundVolume,
    playCaptureSound,
  };
}
