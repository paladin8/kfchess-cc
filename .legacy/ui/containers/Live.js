import amplitude from 'amplitude-js';
import React, { Component } from 'react';
import { Link } from 'react-router-dom';
import { Tooltip } from 'react-tippy';

import SpeedIcon from './SpeedIcon.js';
import Spinner from './Spinner.js';
import UserDisplay from './UserDisplay.js';

export default class Live extends Component {

    constructor(props) {
        super(props);

        this.state = {
            fetching: true,
            activeGames: null,
        };
    }

    componentWillMount() {
        this.setState({ fetching: true });
        this.props.getLiveInfo(data => {
            const activeGames = data && data.games;

            this.setState({
                fetching: false,
                activeGames,
            });
        });
    }


    componentDidMount() {
        amplitude.getInstance().logEvent('Visit Live Page');
    }

    render() {
        const { fetching, activeGames } = this.state;

        return (
            <div className='live'>
                {fetching ?
                    <Spinner />
                    :
                    <div className='live-content'>
                        {this.renderLiveGames(activeGames)}
                    </div>
                }
            </div>
        );
    }

    renderLiveGames(activeGames) {
        return (
            <div className='live-games'>
                <div className='live-games-title'>Live Games</div>
                {activeGames && activeGames.length > 0 ?
                    <table className='live-games-table'>
                        <tbody>
                            {activeGames.map((g, index) => {
                                const gameInfo = g.gameInfo;
                                return (
                                    <tr className='live-games-row' key={index}>
                                        <td className='live-games-speed'>
                                            <SpeedIcon speed={gameInfo.speed} iconOnly={true} rated={false} />
                                        </td>
                                        {this.renderGamePlayers(gameInfo.players)}
                                        <td className='live-games-watch'>
                                            <Tooltip
                                                title='Spectate'
                                            >
                                                <Link
                                                    to={`/game/${g.gameId}`}
                                                    onClick={() => {
                                                        amplitude.getInstance().logEvent('Click Spectate Game', {
                                                            source: 'live',
                                                            players: gameInfo.players,
                                                            gameId: g.gameId,
                                                        });
                                                    }}
                                                >
                                                    <i className='fas fa-eye' />
                                                </Link>
                                            </Tooltip>
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                    :
                    <div className='live-games-empty'>
                        No games are currently live.
                    </div>
                }
            </div>
        );
    }

    renderGamePlayers(players) {
        const { knownUsers } = this.props;

        const playerList = Object.keys(players).sort();

        return (
            <td className='live-games-players'>
                {playerList.map((player, index) => {
                    const value = players[player];
                    if (index === 0) {
                        return (
                            <div className='live-games-players-vs-player' key={index}>
                                <UserDisplay value={value} knownUsers={knownUsers} />
                            </div>
                        );
                    }

                    return (
                        <div className='live-games-players-vs-player' key={index}>
                            <div className='live-games-players-vs'>vs</div>
                            <UserDisplay value={value} knownUsers={knownUsers} />
                        </div>
                    );
                })}
            </td>
        );
    }
};
