import { Link } from 'react-router-dom';
import './ReplayCard.css';
import PlayerBadge from './PlayerBadge';
import { track } from '../analytics';
import { formatDate, formatDuration, formatWinReason } from '../utils/format';
import type { ApiReplaySummary } from '../api/types';

interface ReplayCardProps {
  replay: ApiReplaySummary;
}

export default function ReplayCard({ replay }: ReplayCardProps) {
  // Build the mode label
  let modeLabel: string;
  if (replay.campaign_level_id !== null && replay.campaign_level_id !== undefined) {
    // Campaign games show level number (1-indexed for display)
    modeLabel = `Campaign Level ${replay.campaign_level_id + 1}`;
  } else {
    // Non-campaign games show speed with modifiers
    const isFourPlayer = replay.board_type === 'four_player';
    const modifiers: string[] = [];
    if (isFourPlayer) modifiers.push('4p');
    if (replay.is_ranked) modifiers.push('Rated');

    modeLabel = modifiers.length > 0
      ? `${replay.speed} (${modifiers.join(', ')})`
      : replay.speed;
  }

  return (
    <Link to={`/replay/${replay.game_id}`} className="match-history-item" onClick={() => track('Click Watch Replay', { source: 'replay_card', historyId: replay.game_id })}>
      <div className="match-info">
        <span className="match-date">{formatDate(replay.created_at)}</span>
        <span className="match-speed">{modeLabel}</span>
      </div>
      <div className="match-players">
        {Object.entries(replay.players).map(([num, player]) => (
          <span
            key={num}
            className={`match-player ${replay.winner === parseInt(num) ? 'winner' : ''}`}
          >
            <PlayerBadge
              userId={player.user_id}
              username={player.name || `Player ${num}`}
              pictureUrl={player.picture_url}
              size="sm"
              linkToProfile={false}
            />
          </span>
        ))}
      </div>
      <div className="match-result">
        <span className="match-duration">{formatDuration(replay.total_ticks)}</span>
        {replay.win_reason && (
          <span className="match-reason">{formatWinReason(replay.win_reason)}</span>
        )}
        <span className="like-badge" title={`${replay.likes} likes`}>
          <span className="like-icon">{replay.user_has_liked ? '\u2764\ufe0f' : '\ud83e\udd0d'}</span>
          <span className="like-count">{replay.likes}</span>
        </span>
      </div>
    </Link>
  );
}
