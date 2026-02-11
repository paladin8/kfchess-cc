/**
 * LevelGrid - Component for displaying campaign levels in a grid
 *
 * Shows level cards with status (locked, unlocked, completed) and allows starting levels.
 */

import { useCallback } from 'react';
import type { CampaignLevel } from '../../api/types';
import './LevelGrid.css';

interface LevelGridProps {
  levels: CampaignLevel[];
  onStartLevel: (levelId: number) => void;
  isStarting: boolean;
}

function LevelGrid({ levels, onStartLevel, isStarting }: LevelGridProps) {
  const handleLevelClick = useCallback(
    (level: CampaignLevel) => {
      if (level.isUnlocked && !isStarting) {
        onStartLevel(level.levelId);
      }
    },
    [onStartLevel, isStarting]
  );

  if (levels.length === 0) {
    return (
      <div className="level-grid-empty">
        <p>No levels found for this belt.</p>
      </div>
    );
  }

  return (
    <div className="level-grid">
      {levels.map((level) => (
        <LevelCard
          key={level.levelId}
          level={level}
          onClick={() => handleLevelClick(level)}
          isStarting={isStarting}
        />
      ))}
    </div>
  );
}

interface LevelCardProps {
  level: CampaignLevel;
  onClick: () => void;
  isStarting: boolean;
}

function LevelCard({ level, onClick, isStarting }: LevelCardProps) {
  const levelNumber = (level.levelId % 8) + 1;
  const isLocked = !level.isUnlocked;

  return (
    <button
      className={`level-card ${level.isCompleted ? 'completed' : ''} ${
        isLocked ? 'locked' : ''
      }`}
      onClick={onClick}
      disabled={isLocked || isStarting}
      aria-label={`Level ${levelNumber}: ${level.title}${
        level.isCompleted ? ' (Completed)' : ''
      }${isLocked ? ' (Locked)' : ''}`}
    >
      <div className="level-card-header">
        <span className="level-card-number">{levelNumber}</span>
        <h3 className="level-card-title">{level.title}</h3>
        {level.isCompleted && <span className="level-card-check">&#10003;</span>}
      </div>
      <p className="level-card-description">{level.description}</p>
    </button>
  );
}

export default LevelGrid;
