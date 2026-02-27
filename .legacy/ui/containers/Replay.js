import * as amplitude from '@amplitude/analytics-browser';
import qs from 'query-string';
import React, { Component } from 'react';
import { CopyToClipboard } from 'react-copy-to-clipboard';
import { Tooltip } from 'react-tippy';

import GameBoard from './GameBoard.js';
import SpeedIcon from './SpeedIcon.js';
import UserDisplay from './UserDisplay.js';
import GameState from '../util/GameState.js';
import * as Time from '../util/Time.js';

export default class Replay extends Component {

    constructor(props) {
        super(props);

        this.state = {
            gameState: null,

            currentTick: 0,
            gameFinished: true,
            game: null,
            windowWidth: window.innerWidth,
            windowHeight: window.innerHeight,

            musicVolume: (window.localStorage && window.localStorage.musicVolume) || 0,
            soundVolume: (window.localStorage && window.localStorage.soundVolume) || 0,
        };

        this.resize = this.resize.bind(this);
        this.update = this.update.bind(this);

        this.music = null;
        this.captureSounds = [];
        this.finishSound = null;
    }

    componentWillMount() {
        const { match, location, history } = this.props;
        const historyId = match.params.historyId;

        const { gameId } = qs.parse(location.search);

        if (gameId) {
            this.initGameState(gameId);
        } else {
            this.props.startReplay(historyId, data => {
                history.push(`/replay/${historyId}?gameId=${data.gameId}`);
                this.initGameState(data.gameId);
            });
        }
    }

    componentDidMount() {
        const { match } = this.props;
        const historyId = match.params.historyId;

        amplitude.track('Watch Replay', {
            historyId,
        });
    }

    initGameState(gameId) {
        const gameState = new GameState(gameId, undefined, this.props.fetchUserInfo, () => {});
        this.setState({ gameState });

        // listen for updates
        gameState.registerListener(this.update);

        // listen for resizes
        window.addEventListener('resize', this.resize);

        this.interval = setInterval(() => {
            this.setState({
                currentTick: gameState.getCurrentTick(),
            });
        }, 1000);
    }

    componentWillUnmount() {
        clearInterval(this.interval);

        window.removeEventListener('resize', this.resize);

        if (this.state.gameState) {
            this.state.gameState.unregisterListener(this.update);
            this.state.gameState.destroy();
        }
    }

    resize() {
        this.setState({
            windowWidth: window.innerWidth,
            windowHeight: window.innerHeight,
        });
    }

    update(gameState, updates) {
        const { gameFinished, soundVolume } = this.state;

        if (!gameFinished && gameState.game && gameState.game.finished) {
            if (this.finishSound) {
                this.finishSound.volume = soundVolume / 100;
                this.finishSound.play();
            }
        }

        const hasCapture = updates && updates.some(u => u.type === 'capture');
        if (hasCapture && this.captureSounds.length > 0) {
            const soundIndex = Math.floor(Math.random() * this.captureSounds.length);
            const randomSound = this.captureSounds[soundIndex];
            randomSound.volume = soundVolume / 100;
            randomSound.play();
        }

        this.setState({
            currentTick: gameState.getCurrentTick(),
            gameFinished: gameState.game ? gameState.game.finished : gameFinished,
            game: gameState.game,
        });
    }

    render() {
        const {
            gameState,
            currentTick,
            game,
            windowWidth,
            windowHeight,
            musicVolume,
            soundVolume,
        } = this.state;

        const { match, knownUsers } = this.props;

        const historyId = match.params.historyId;
        const baseUrl = `${window.location.origin}${window.location.pathname}`;

        const totalTicks = gameState ? gameState.ticks : 0;

        const isPortrait = windowHeight > 1.5 * windowWidth;

        if (this.music) {
            if (game && game.started && !game.finished) {
                this.music.play();
            } else {
                this.music.pause();
                this.music.currentTime = 0;
            }
        }

        return game ?
            <div className='game'>
                <div className='game-content'>
                    {this.renderAudio()}
                    <div className='game-board'>
                        <GameBoard gameState={gameState} />
                    </div>
                    <div className='game-meta'>
                        <div>
                            <div className='game-meta-section game-time'>
                                {Time.renderGameTime(currentTick) + ' / ' + Time.renderGameTime(totalTicks)}
                            </div>
                            <div className='game-meta-section'>
                                <Tooltip
                                    title='Copied to clipboard!'
                                    distance={5}
                                    trigger='click'
                                >
                                    <CopyToClipboard
                                        text={baseUrl}
                                        onCopy={() => {
                                            amplitude.track('Copy Replay Link', {
                                                source: 'sidebar',
                                                gameId: gameState.gameId,
                                                historyId,
                                            });
                                        }}
                                    >
                                        <div className='game-friend-link'>
                                            <div className='game-friend-link-text'>
                                                Copy permanent link
                                            </div>
                                            <div className='game-friend-link-icon'>
                                                <i className='fas fa-link' />
                                            </div>
                                        </div>
                                    </CopyToClipboard>
                                </Tooltip>
                            </div>
                            <div className='game-meta-section game-meta-players'>
                                <table>
                                    <tbody>
                                        <tr className='game-meta-player'>
                                            <td className='game-meta-player-color'>White:</td>
                                            <td><UserDisplay value={game.players[1]} knownUsers={knownUsers} /></td>
                                        </tr>
                                        <tr className='game-meta-player'>
                                            <td className='game-meta-player-color'>Black:</td>
                                            <td><UserDisplay value={game.players[2]} knownUsers={knownUsers} /></td>
                                        </tr>
                                    </tbody>
                                </table>
                            </div>
                        </div>
                        <div className='game-audio-controls'>
                            <table>
                                <tbody>
                                    <tr className='game-audio-control'>
                                        <td className='game-audio-control-label'>Music:</td>
                                        <td>
                                            <input
                                                className='game-music-volume'
                                                type='range'
                                                min='0'
                                                max='100'
                                                value={musicVolume}
                                                onChange={() => {}}
                                                onInput={e => {
                                                    amplitude.track('Change Volume', {
                                                        source: 'replay',
                                                        type: 'music',
                                                        volume: e.target.value,
                                                    });

                                                    this.setState({ musicVolume : e.target.value });
                                                    if (window.localStorage) {
                                                        window.localStorage.musicVolume = e.target.value;
                                                    }
                                                }}
                                            />
                                        </td>
                                    </tr>
                                    <tr className='game-audio-control'>
                                        <td className='game-audio-control-label'>Sound:</td>
                                        <td>
                                            <input
                                                className='game-sound-volume'
                                                type='range'
                                                min='0'
                                                max='100'
                                                value={soundVolume}
                                                onChange={() => {}}
                                                onInput={e => {
                                                    amplitude.track('Change Volume', {
                                                        source: 'replay',
                                                        type: 'sound',
                                                        volume: e.target.value,
                                                    });

                                                    this.setState({ soundVolume : e.target.value });
                                                    if (window.localStorage) {
                                                        window.localStorage.soundVolume = e.target.value;
                                                    }
                                                }}
                                            />
                                        </td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
                {isPortrait &&
                    <div className='game-portrait-warning'>
                        Your browser appears to be in portrait mode.<br/>
                        Rotate for a better experience!
                    </div>
                }
            </div>
            :
            null;
    }

    renderAudio() {
        const { musicVolume } = this.state;

        return (
            <div>
                <audio
                    ref={music => {
                        this.music = music;
                        if (this.music) {
                            this.music.volume = musicVolume / 100;
                        }
                    }}
                    loop
                >
                    <source src='/static/kfchess-music.mp3' type='audio/mp3' />
                </audio>
                <audio ref={sound => this.captureSounds[0] = sound}>
                    <source src='/static/kfchess-sound1.mp3' type='audio/mp3' />
                </audio>
                <audio ref={sound => this.captureSounds[1] = sound}>
                    <source src='/static/kfchess-sound2.mp3' type='audio/mp3' />
                </audio>
                <audio ref={sound => this.captureSounds[2] = sound}>
                    <source src='/static/kfchess-sound3.mp3' type='audio/mp3' />
                </audio>
                <audio ref={sound => this.captureSounds[3] = sound}>
                    <source src='/static/kfchess-sound4.mp3' type='audio/mp3' />
                </audio>
                <audio ref={sound => this.captureSounds[4] = sound}>
                    <source src='/static/kfchess-sound5.mp3' type='audio/mp3' />
                </audio>
                <audio ref={sound => this.captureSounds[5] = sound}>
                    <source src='/static/kfchess-sound6.mp3' type='audio/mp3' />
                </audio>
                <audio ref={sound => this.captureSounds[6] = sound}>
                    <source src='/static/kfchess-sound7.mp3' type='audio/mp3' />
                </audio>
                <audio ref={sound => this.captureSounds[7] = sound}>
                    <source src='/static/kfchess-sound8.mp3' type='audio/mp3' />
                </audio>
                <audio ref={sound => this.finishSound = sound}>
                    <source src='/static/kfchess-gong.mp3' type='audio/mp3' />
                </audio>
            </div>
        );
    }
};
