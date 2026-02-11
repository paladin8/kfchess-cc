/**
 * Audio Controls Component
 *
 * Volume sliders for music and sound effects.
 */

import { track } from '../../analytics';
import './AudioControls.css';

interface AudioControlsProps {
  musicVolume: number;
  soundVolume: number;
  onMusicVolumeChange: (volume: number) => void;
  onSoundVolumeChange: (volume: number) => void;
}

export function AudioControls({
  musicVolume,
  soundVolume,
  onMusicVolumeChange,
  onSoundVolumeChange,
}: AudioControlsProps) {
  return (
    <div className="audio-controls">
      <div className="audio-control">
        <label className="audio-control-label">Music:</label>
        <input
          type="range"
          className="audio-control-slider"
          min="0"
          max="100"
          value={musicVolume}
          onChange={(e) => { const v = parseInt(e.target.value, 10); onMusicVolumeChange(v); track('Change Volume', { source: 'game', type: 'music', volume: v }); }}
        />
      </div>
      <div className="audio-control">
        <label className="audio-control-label">Sound:</label>
        <input
          type="range"
          className="audio-control-slider"
          min="0"
          max="100"
          value={soundVolume}
          onChange={(e) => { const v = parseInt(e.target.value, 10); onSoundVolumeChange(v); track('Change Volume', { source: 'game', type: 'sound', volume: v }); }}
        />
      </div>
    </div>
  );
}
