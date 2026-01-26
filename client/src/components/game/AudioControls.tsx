/**
 * Audio Controls Component
 *
 * Volume sliders for music and sound effects.
 */

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
          onChange={(e) => onMusicVolumeChange(parseInt(e.target.value, 10))}
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
          onChange={(e) => onSoundVolumeChange(parseInt(e.target.value, 10))}
        />
      </div>
    </div>
  );
}
