const playerDirection = [0, -1, 1];

const pieceToLegalMoveFn = {
    'P': isPawnLegalMove,
    'N': isKnightLegalMove,
    'B': isBishopLegalMove,
    'R': isRookLegalMove,
    'Q': isQueenLegalMove,
    'K': isKingLegalMove,
};

export function getPieceById(game, pieceId) {
    for (let i = 0; i < game.board.pieces.length; i++) {
        const piece = game.board.pieces[i];
        if (piece.id === pieceId) {
            return piece;
        }
    }
    return null;
}

export function getPieceByLocation(game, toRow, toCol) {
    for (let i = 0; i < game.board.pieces.length; i++) {
        const piece = game.board.pieces[i];
        if (!piece.captured && piece.row === toRow && piece.col === toCol) {
            return piece;
        }
    }
    return null;
}

export function isMoving(game, piece) {
    for (let i = 0; i < game.activeMoves.length; i++) {
        const move = game.activeMoves[i];
        if (move.pieceId === piece.id) {
            return true;
        }
    }
    return false;
}

export function isCooldown(game, piece) {
    for (let i = 0; i < game.cooldowns.length; i++) {
        const cooldown = game.cooldowns[i];
        if (cooldown.pieceId === piece.id) {
            return true;
        }
    }
    return false;
}

function isLegalMoveNoCross(game, currentTick, piece, rowDir, colDir, steps, capture) {
    for (let i = 1; i <= steps; i++) {
        const iRow = piece.row + rowDir * i, iCol = piece.col + colDir * i;

        // check for not moving pieces
        const iPiece = getPieceByLocation(game, iRow, iCol);
        if (
            iPiece && !iPiece.captured && !isMoving(game, iPiece) &&
            (!capture || i !== steps || iPiece.player === piece.player || isMoving(game, iPiece))
        ) {
            return false;
        }

        // check for the same player's moving pieces
        for (let j = 0; j < game.activeMoves.length; j++) {
            const move = game.activeMoves[j];
            const endPos = move.moveSeq[move.moveSeq.length - 1];
            if (move.player === piece.player && endPos[0] === iRow && endPos[1] === iCol) {
                return false;
            }
        }
    }

    // the destination cannot be on the future path of any of the same player's moves
    const eRow = piece.row + rowDir * steps, eCol = piece.col + colDir * steps;
    for (let i = 0; i < game.activeMoves.length; i++) {
        const move = game.activeMoves[i];
        if (move.player !== piece.player) {
            continue;
        }

        const tickDelta = currentTick - move.startingTick;
        const movements = Math.floor((tickDelta + game.moveTicks - 1) / game.moveTicks);
        for (let j = movements; j < move.moveSeq.length; j++) {
            if (move.moveSeq[j][0] === eRow && move.moveSeq[j][1] === eCol) {
                return false;
            }
        }
    }

    return true;
}

function isPawnLegalMove(game, currentTick, piece, toRow, toCol) {
    // pawns must move one row in the player's direction unless it is the first move
    let canCapture = true;
    const dir = playerDirection[piece.player];
    const steps = Math.abs(toRow - piece.row);
    if (toRow - piece.row !== dir) {
        if (piece.player === 1 && piece.row === 6 && toRow === 4) {
            canCapture = false;
        } else if (piece.player === 2 && piece.row === 1 && toRow === 3) {
            canCapture = false;
        } else {
            return false;
        }
    }

    // if it is not changing column, it must move to an empty location
    if (piece.col === toCol) {
        const isLegal = isLegalMoveNoCross(game, currentTick, piece, dir, 0, steps, false);
        if (isLegal) {
            return true;
        }
    }

    // if it is changing column by 1, it must be capturing
    if (canCapture && (piece.col + 1 === toCol || piece.col - 1 === toCol)) {
        const destPiece = getPieceByLocation(game, toRow, toCol);
        if (destPiece && destPiece.player !== piece.player && !isMoving(game, destPiece)) {
            const isLegal = isLegalMoveNoCross(game, currentTick, piece, dir, toCol - piece.col, steps, true);
            if (isLegal) {
                return true;
            }
        }
    }

    return false;
}

function isKnightLegalMove(game, currentTick, piece, toRow, toCol) {
    const rowDelta = Math.abs(toRow - piece.row), colDelta = Math.abs(toCol - piece.col);
    if (!((rowDelta === 1 && colDelta === 2) || (rowDelta === 2 && colDelta === 1))) {
        return false;
    }

    return isLegalMoveNoCross(game, currentTick, piece, toRow - piece.row, toCol - piece.col, 1, true);
}

function isBishopLegalMove(game, currentTick, piece, toRow, toCol) {
    const rowDelta = Math.abs(toRow - piece.row), colDelta = Math.abs(toCol - piece.col);
    if (rowDelta !== colDelta) {
        return false;
    }

    const rowDir = (toRow - piece.row) / rowDelta;
    const colDir = (toCol - piece.col) / colDelta;
    return isLegalMoveNoCross(game, currentTick, piece, rowDir, colDir, rowDelta, true);
}

function isRookLegalMove(game, currentTick, piece, toRow, toCol) {
    const rowDelta = Math.abs(toRow - piece.row), colDelta = Math.abs(toCol - piece.col);
    if (rowDelta > 0 && colDelta > 0) {
        return false;
    }

    const rowDir = rowDelta > 0 ? (toRow - piece.row) / rowDelta : 0;
    const colDir = colDelta > 0 ? (toCol - piece.col) / colDelta : 0;
    return isLegalMoveNoCross(game, currentTick, piece, rowDir, colDir, Math.max(rowDelta, colDelta), true);
}

function isQueenLegalMove(game, currentTick, piece, toRow, toCol) {
    return isBishopLegalMove(game, currentTick, piece, toRow, toCol) || isRookLegalMove(game, currentTick, piece, toRow, toCol);
}

function isKingLegalMove(game, currentTick, piece, toRow, toCol) {
    const rowDelta = Math.abs(toRow - piece.row), colDelta = Math.abs(toCol - piece.col);
    if (rowDelta > 1 || colDelta > 1) {
        // check for castling
        if (!piece.moved && rowDelta === 0 && (toCol === 2 || toCol === 6)) {
            const rookCol = toCol === 2 ? 0 : 7;
            const rookToCol = toCol === 2 ? 3 : 5;
            const rookPiece = getPieceByLocation(game, piece.row, rookCol);
            if (rookPiece && !rookPiece.moved) {
                const isKingLegal = isRookLegalMove(game, currentTick, piece, toRow, toCol);
                const isRookLegal = isRookLegalMove(game, currentTick, rookPiece, toRow, rookToCol);
                return isKingLegal && isRookLegal;
            }
        }

        return false;
    }

    return isQueenLegalMove(game, currentTick, piece, toRow, toCol);
}

export function isLegalMove(game, currentTick, piece, toRow, toCol) {
    if (toRow < 0 || toRow >= 8 || toCol < 0 || toCol >= 8) {
        return false;
    }

    if (piece.row === toRow && piece.col === toCol) {
        return false;
    }

    return pieceToLegalMoveFn[piece.type](game, currentTick, piece, toRow, toCol);
}
