import React, { Component } from 'react';
import * as PIXI from 'pixi.js';

import chessboardImg from '../assets/chessboard.png';
import chessboardBlackImg from '../assets/chessboard-black.png';
import * as gameLogic from '../util/GameLogic.js';
import sprites from '../util/Sprites.js';

const BORDER_FACTOR = 0.08341323;
const SHIFT_FACTOR = 0.005;
const SPRITE_FACTOR = 0.90;

const TOP_EDGE_PADDING = 4;

const COOLDOWN_COLOR = 0xf0f000;
const BACKGROUND_COLOR = 0xfcfcf4;

export default class GameBoard extends Component {

    constructor(props) {
        super(props);

        this.state = {
            player: null,
            ready: false,
        };

        this.resize = this.resize.bind(this);
        this.update = this.update.bind(this);
        this.handleClick = this.handleClick.bind(this);
        this.handleMove = this.handleMove.bind(this);

        this.pieceSprites = {};
        this.selected = null;
        this.dragging = false;
    }

    componentDidMount() {
        // create app
        this.dim = this.getDim();
        this.border = this.dim * BORDER_FACTOR;
        this.shift = this.dim * SHIFT_FACTOR;
        this.cellDim = (this.dim - 2 * this.border) / 8;
        this.cellPadding = this.cellDim * (1 - SPRITE_FACTOR) / 2;

        this.app = new PIXI.Application(this.dim, this.dim - this.border + TOP_EDGE_PADDING, {
            view: this.canvas,
        });

        this.backgroundTexture = new PIXI.Graphics();
        this.backgroundTexture.beginFill(BACKGROUND_COLOR);
        this.backgroundTexture.drawRect(0, 0, this.dim, this.dim - this.border + TOP_EDGE_PADDING);

        const chessboardTexture = PIXI.Texture.fromImage(chessboardImg);
        this.chessboardSprite = new PIXI.Sprite(chessboardTexture);
        this.chessboardSprite.y = - this.border + TOP_EDGE_PADDING;
        this.chessboardSprite.width = this.dim;
        this.chessboardSprite.height = this.dim;

        this.app.stage.interactive = true;
        this.app.stage.pointerdown = (e) => this.handleClick(e, true);
        this.app.stage.pointermove = this.handleMove;
        this.app.stage.pointerup = (e) => this.handleClick(e, false);

        this.app.stage.addChild(this.backgroundTexture);
        this.app.stage.addChild(this.chessboardSprite);

        this.metaStage = new PIXI.Container();
        this.app.stage.addChild(this.metaStage);

        this.mainStage = new PIXI.Container();
        this.app.stage.addChild(this.mainStage);

        this.app.ticker.add(this.update);

        window.addEventListener('resize', this.resize);
    }

    componentWillUnmount() {
        this.unselect();

        window.removeEventListener('resize', this.resize);

        // destroy all sprites
        for (let pieceId in this.pieceSprites) {
            const pieceSprite = this.pieceSprites[pieceId];
            this.destroyPieceSprite(pieceSprite);
        }

        this.backgroundTexture.destroy();
        this.chessboardSprite.destroy();

        this.mainStage.destroy();
        this.metaStage.destroy();

        this.app.ticker.destroy();
        this.app.stage.destroy();
    }

    componentWillReceiveProps(nextProps) {
        if (this.props.gameState !== nextProps.gameState) {
            // destroy all sprites
            for (let pieceId in this.pieceSprites) {
                const pieceSprite = this.pieceSprites[pieceId];
                this.destroyPieceSprite(pieceSprite);
            }

            this.pieceSprites = {};
            this.unselect();
        }
    }

    resize() {
        this.dim = this.getDim();
        this.border = this.dim * BORDER_FACTOR;
        this.shift = this.dim * SHIFT_FACTOR;
        this.cellDim = (this.dim - 2 * this.border) / 8;
        this.cellPadding = this.cellDim * (1 - SPRITE_FACTOR) / 2;

        this.backgroundTexture.clear();
        this.backgroundTexture.beginFill(BACKGROUND_COLOR);
        this.backgroundTexture.drawRect(0, 0, this.dim, this.dim - this.border + TOP_EDGE_PADDING);

        this.chessboardSprite.y = - this.border + TOP_EDGE_PADDING;
        this.chessboardSprite.width = this.dim;
        this.chessboardSprite.height = this.dim;

        this.app.renderer.resize(this.dim, this.dim - this.border + TOP_EDGE_PADDING);
    }

    getDim() {
        const windowWidth = window.innerWidth, windowHeight = window.innerHeight;
        return Math.max(480, Math.min(windowWidth - 240, windowHeight - 40, 720));
    }

    destroyPieceSprite(pieceSprite) {
        pieceSprite.sprite.destroy();
        pieceSprite.cooldownGraphics.destroy(true);
        pieceSprite.borderGraphics.destroy(true);
        this.mainStage.removeChild(pieceSprite.sprite);
        this.metaStage.removeChild(pieceSprite.cooldownGraphics);
        this.metaStage.removeChild(pieceSprite.borderGraphics);
    }

    update() {
        const { gameState } = this.props;
        const { game } = gameState;
        if (!game) {
            return;
        }

        if (!this.state.ready) {
            this.setState({ ready: true });
        }

        if (gameState.player !== this.state.player) {
            this.setState({ player: gameState.player });

            if (gameState.player === 2) {
                const chessboardTexture = PIXI.Texture.fromImage(chessboardBlackImg);
                this.chessboardSprite.setTexture(chessboardTexture);
            }
        }

        if (!game.started) {
            this.unselect();
        }

        const currentTick = gameState.getCurrentTick();

        const movingPieces = {};
        for (let i = 0; i < game.moveLog.length; i++) {
            const move = game.moveLog[i];
            const totalMoveTicks = (move.moveSeq.length - 1) * game.moveTicks;
            if (currentTick <= move.startingTick + totalMoveTicks + 10) {
                movingPieces[move.pieceId] = move;
            }
        }

        for (let i = 0; i < game.activeMoves.length; i++) {
            const move = game.activeMoves[i];
            movingPieces[move.pieceId] = move;
        }

        const cooldownPieces = {};
        for (let i = 0; i < game.cooldowns.length; i++) {
            const cooldown = game.cooldowns[i];
            if (currentTick >= cooldown.startingTick) {
                cooldownPieces[cooldown.pieceId] = cooldown;
            }
        }

        const allPieces = {};
        game.board.pieces.forEach(piece => {
            allPieces[piece.id] = true;
        });

        // destroy pieces that are gone (e.g. due to game reset)
        for (let pieceId in this.pieceSprites) {
            if (!(pieceId in allPieces)) {
                const pieceSprite = this.pieceSprites[pieceId];
                this.destroyPieceSprite(pieceSprite);
                delete this.pieceSprites[pieceId];
            }
        }

        // render pieces
        game.board.pieces.forEach(piece => {
            const key = piece.type + piece.player;

            // check for when selected piece is captured
            if (piece.captured && this.selected && this.selected.piece.id === piece.id) {
                this.unselect();
            }

            let pieceSprite = this.pieceSprites[piece.id]
            if (!pieceSprite || pieceSprite.key !== key) {
                // create sprite if it doesn't exist already or the key changed
                if (pieceSprite) {
                    this.destroyPieceSprite(pieceSprite);
                }

                const spriteFn = sprites[key];
                if (spriteFn) {
                    pieceSprite = {key, sprite: spriteFn()};
                    pieceSprite.sprite.x = -1;
                    this.mainStage.addChild(pieceSprite.sprite);

                    pieceSprite.cooldownGraphics = new PIXI.Graphics();
                    this.metaStage.addChild(pieceSprite.cooldownGraphics);

                    pieceSprite.borderGraphics = new PIXI.Graphics();
                    this.metaStage.addChild(pieceSprite.borderGraphics);

                    this.pieceSprites[piece.id] = pieceSprite
                }
            }

            if (pieceSprite) {
                if (piece.captured) {
                    // don't show captured pieces
                    pieceSprite.sprite.visible = false;
                } else {
                    pieceSprite.sprite.visible = true;
                    pieceSprite.sprite.width = this.cellDim * SPRITE_FACTOR;
                    pieceSprite.sprite.height = this.cellDim * SPRITE_FACTOR;

                    let pRow, pCol;
                    if (piece.id in movingPieces && pieceSprite.sprite.x >= 0) {
                        // moving piece sprites are re-added to stage so they appear on top
                        this.mainStage.removeChild(pieceSprite.sprite);
                        this.mainStage.addChild(pieceSprite.sprite);

                        // compute interpolated position of the moving piece
                        const move = movingPieces[piece.id]
                        const totalMoveTicks = (move.moveSeq.length - 1) * game.moveTicks;
                        const interp = Math.max(0, Math.min(1, (currentTick - move.startingTick) / totalMoveTicks));
                        const sRow = move.moveSeq[0][0], sCol = move.moveSeq[0][1];
                        const eRow = move.moveSeq[move.moveSeq.length - 1][0], eCol = move.moveSeq[move.moveSeq.length - 1][1];

                        // compute current position's interpolation factor
                        const sPosition = this.getPosition(sRow, sCol);
                        const ePosition = this.getPosition(eRow, eCol);
                        let currentInterp = 0;
                        if (ePosition.x !== sPosition.x) {
                            currentInterp = (pieceSprite.sprite.x - sPosition.x) / (ePosition.x - sPosition.x);
                        } else if (ePosition.y !== sPosition.y) {
                            currentInterp = (pieceSprite.sprite.y - sPosition.y) / (ePosition.y - sPosition.y);
                        }

                        // bound the number of ticks we skip rendering
                        const tickLimit = 0.5;
                        const finalInterp = Math.min(interp, currentInterp + tickLimit / totalMoveTicks);

                        pRow = sRow + (eRow - sRow) * finalInterp;
                        pCol = sCol + (eCol - sCol) * finalInterp;
                    } else {
                        pRow = piece.row;
                        pCol = piece.col;
                    }

                    const position = this.getPosition(pRow, pCol);
                    pieceSprite.sprite.x = position.x;
                    pieceSprite.sprite.y = position.y;

                    // for debugging
                    // pieceSprite.borderGraphics.clear();
                    // pieceSprite.borderGraphics.lineStyle(1, 0x000000);
                    // pieceSprite.borderGraphics.drawRect(position.x, position.y, this.cellDim, this.cellDim);
                }
            }
        });

        // render selected if necessary
        if (this.selected) {
            if (!this.selected.graphicsAdded) {
                this.metaStage.addChild(this.selected.graphics);
                this.selected.graphicsAdded = true;
            }

            const position = this.getPosition(this.selected.piece.row, this.selected.piece.col);

            if (
                this.selected.graphicsX !== position.x ||
                this.selected.graphicsY !== position.y ||
                this.selected.cellDim !== this.cellDim
            ) {
                this.selected.graphics.clear();
                this.selected.graphics.lineStyle(4, COOLDOWN_COLOR);
                this.selected.graphics.drawRect(position.x + 1, position.y + 1, this.cellDim - 2, this.cellDim - 2);

                this.selected.graphicsX = position.x;
                this.selected.graphicsY = position.y;
                this.selected.cellDim = this.cellDim;
            }

            if (
                !gameLogic.isCooldown(game, this.selected.piece) &&
                gameLogic.isLegalMove(game, currentTick, this.selected.piece, this.selected.row, this.selected.col)
            ) {
                // selected piece sprite is re-added to the stage so it appears on top
                this.mainStage.removeChild(this.selected.sprite);
                this.mainStage.addChild(this.selected.sprite);

                const selectedPosition = this.getPosition(this.selected.row, this.selected.col);
                this.selected.sprite.x = selectedPosition.x;
                this.selected.sprite.y = selectedPosition.y;
                this.selected.sprite.width = this.cellDim * SPRITE_FACTOR;
                this.selected.sprite.height = this.cellDim * SPRITE_FACTOR;
                this.selected.sprite.alpha = 0.3;
            } else {
                this.mainStage.removeChild(this.selected.sprite);
            }
        }

        // render cooldowns if necessary
        for (let pieceId in this.pieceSprites) {
            const pieceSprite = this.pieceSprites[pieceId];
            if (pieceId in cooldownPieces) {
                const cooldown = cooldownPieces[pieceId];
                const interp = Math.max(0, Math.min(1, (currentTick - cooldown.startingTick) / game.cooldownTicks));
                const piece = gameLogic.getPieceById(game, cooldown.pieceId);
                const finishing = (1 - interp) * game.cooldownTicks < 2;

                this.updateCooldownGraphics(pieceSprite.cooldownGraphics, piece.row, piece.col, interp, finishing);
            } else {
                pieceSprite.cooldownGraphics.visible = false;

                if (pieceId in movingPieces) {
                    // special case for the end of a move, start rendering cooldown even if server hasn't updated us yet
                    const move = movingPieces[pieceId];
                    const piece = gameLogic.getPieceById(game, move.pieceId);
                    if (!piece.captured) {
                        const totalMoveTicks = (move.moveSeq.length - 1) * game.moveTicks;
                        if (currentTick - move.startingTick >= totalMoveTicks) {
                            const lastMove = move.moveSeq[move.moveSeq.length - 1];
                            const interp = (currentTick - move.startingTick - totalMoveTicks) / game.cooldownTicks;
                            this.updateCooldownGraphics(pieceSprite.cooldownGraphics, lastMove[0], lastMove[1], interp, false);
                        }
                    }
                }
            }
        }
    }

    updateCooldownGraphics(cooldownGraphics, row, col, interp, finishing) {
        interp = Math.max(0, Math.min(interp, 1));

        cooldownGraphics.visible = true;
        cooldownGraphics.clear();
        cooldownGraphics.beginFill(COOLDOWN_COLOR, 0.5);

        const offset = this.cellDim * interp, remaining = this.cellDim - offset;
        const position = this.getPosition(row, col);
        cooldownGraphics.drawRect(position.x, position.y + offset, this.cellDim, remaining);

        if (finishing) {
            cooldownGraphics.endFill();
            cooldownGraphics.lineStyle(4, COOLDOWN_COLOR);
            cooldownGraphics.drawRect(position.x + 1, position.y + 1, this.cellDim - 2, this.cellDim - 2);
        }
    }

    handleClick(event, down) {
        if (!down && !this.dragging) {
            return;
        }

        this.dragging = false;

        const { gameState } = this.props;
        if (!gameState.game.started || gameState.game.finished) {
            // don't allow clicks before game starts or after game finishes
            return;
        }

        const { row, col, piece } = this.getClickedPiece(event.data.originalEvent);

        let shouldSelect = true;
        if (this.selected) {
            if (piece && this.selected.piece.id === piece.id) {
                shouldSelect = false;
            } else if (!gameLogic.isLegalMove(gameState.game, gameState.getCurrentTick(), this.selected.piece, row, col)) {
                this.unselect();
            } else if (gameLogic.isCooldown(gameState.game, this.selected.piece)) {
                shouldSelect = false;
            } else {
                if (!piece || this.selected.piece.player !== piece.player) {
                    gameState.move(this.selected.piece.id, this.selected.piece.player, row, col);
                }
                this.unselect();
                shouldSelect = false;
            }
        }

        if (piece && piece.player === gameState.player && shouldSelect) {
            const key = piece.type + piece.player;
            const sprite = sprites[key]();
            const graphics = new PIXI.Graphics();

            this.selected = {
                piece,
                row,
                col,
                sprite,
                graphics,
            };
        }
    }

    getPosition(row, col) {
        const { player } = this.props.gameState;

        if (player === 1 || player === 0) {
            return {
                x: Math.round(this.border + col * this.cellDim + this.cellPadding - this.shift),
                y: Math.round(TOP_EDGE_PADDING + row * this.cellDim + this.cellPadding - this.shift),
            };
        } else {
            return {
                x: Math.round(this.border + (7 - col) * this.cellDim + this.cellPadding - this.shift),
                y: Math.round(TOP_EDGE_PADDING + (7 - row) * this.cellDim + this.cellPadding - this.shift),
            };
        }
    }

    unselect() {
        if (this.selected) {
            this.selected.sprite.destroy();
            this.selected.graphics.destroy(true);
            this.mainStage.removeChild(this.selected.sprite);
            this.metaStage.removeChild(this.selected.graphics);
            this.selected = null;
        }
    }

    handleMove(event) {
        this.dragging = true;

        const { row, col, piece } = this.getClickedPiece(event.data.originalEvent);

        if (this.selected) {
            this.selected.row = row;
            this.selected.col = col;
        }
    }

    getClickedPiece(event) {
        const canvasRect = this.canvas.getBoundingClientRect();

        let adjustedX, adjustedY;
        if (event.changedTouches) {
            adjustedX = event.changedTouches[0].clientX - canvasRect.x;
            adjustedY = event.changedTouches[0].clientY - canvasRect.y;
        } else {
            adjustedX = event.clientX - canvasRect.x;
            adjustedY = event.clientY - canvasRect.y;
        }

        const point = new PIXI.Point(adjustedX, adjustedY);

        let row = Math.floor(adjustedY / this.cellDim);
        let col = Math.floor((adjustedX - this.border) / this.cellDim);
        if (this.props.gameState.player === 2) {
            row = 7 - row;
            col = 7 - col;
        }

        // find if click landed on any piece
        for (let pieceId in this.pieceSprites) {
            const pieceSprite = this.pieceSprites[pieceId];
            if (!pieceSprite.sprite.visible) {
                continue;
            }

            const { game } = this.props.gameState;
            const piece = gameLogic.getPieceById(game, pieceId);
            if (
                pieceSprite.sprite.containsPoint(point) &&
                !gameLogic.isMoving(game, piece)
            ) {
                return { row, col, piece };
            }
        }

        return { row, col };
    }

    render() {
        const { ready } = this.state;

        return <canvas ref={ref => this.canvas = ref} style={{ display: (ready ? '' : 'none')}} />
    }
};
