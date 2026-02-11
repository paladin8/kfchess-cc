/**
 * DrawOfferButton Component
 *
 * Offer Draw / Accept Draw button for active players during gameplay.
 */

import { useGameStore, selectIsPlayerEliminated } from '../../stores/game';
import { track } from '../../analytics';

export function DrawOfferButton() {
  const playerNumber = useGameStore((s) => s.playerNumber);
  const status = useGameStore((s) => s.status);
  const isEliminated = useGameStore(selectIsPlayerEliminated);
  const drawOffers = useGameStore((s) => s.drawOffers);
  const players = useGameStore((s) => s.players);
  const pieces = useGameStore((s) => s.pieces);
  const offerDraw = useGameStore((s) => s.offerDraw);

  // Only show for active players during gameplay who haven't been eliminated
  if (playerNumber === 0 || status !== 'playing' || isEliminated) {
    return null;
  }

  // Count other active humans and check if they've all offered
  let otherHumanCount = 0;
  let otherHumansAllOffered = false;
  if (players) {
    let allOffered = true;
    for (const [numStr, player] of Object.entries(players)) {
      const num = Number(numStr);
      if (num === playerNumber) continue;
      if (player.is_bot) continue;
      const king = pieces.find((p) => p.type === 'K' && p.player === num);
      if (king?.captured) continue;
      otherHumanCount++;
      if (!drawOffers.includes(num)) allOffered = false;
    }
    otherHumansAllOffered = otherHumanCount > 0 && allOffered;
  }

  // Don't show if there are no other human players (all opponents are bots)
  if (otherHumanCount === 0) {
    return null;
  }

  const alreadyOffered = drawOffers.includes(playerNumber);

  const buttonText = alreadyOffered
    ? 'Draw Offered'
    : otherHumansAllOffered
      ? 'Accept Draw'
      : 'Offer Draw';

  const handleClick = () => {
    const { gameId } = useGameStore.getState();
    track('Offer Draw', { gameId, player: playerNumber });
    offerDraw();
  };

  return (
    <button
      className={`draw-offer-button${alreadyOffered ? ' draw-offered' : ''}`}
      onClick={handleClick}
      disabled={alreadyOffered}
    >
      {buttonText}
    </button>
  );
}
