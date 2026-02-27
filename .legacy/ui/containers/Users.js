import * as amplitude from '@amplitude/analytics-browser';
import React, { Component } from 'react';
import { Link } from 'react-router-dom';
import { Tooltip } from 'react-tippy';
import { CSSTransition } from 'react-transition-group'

import UserDisplay from './UserDisplay.js';

export default class Users extends Component {

    constructor(props) {
        super(props);

        this.state = {
            trayOpen: false,
        };
    }

    render() {
        const { trayOpen } = this.state;
        const { onlineUsers } = this.props;

        return (
            <div className='online-users'>
                <div
                    className='online-users-button'
                    onClick={() => {
                        this.props.onOpen();
                        this.setState({ trayOpen: !trayOpen });
                    }}
                >
                    <div className='online-users-icon-wrapper'>
                        <CSSTransition
                            in={!trayOpen}
                            timeout={500}
                            classNames='users-transition'
                        >
                            <i className={`fas fa-users online-users-icon ${!trayOpen ? 'online-users-icon-showing' : ''}`} />
                        </CSSTransition>
                        <CSSTransition
                            in={trayOpen}
                            timeout={500}
                            classNames='times-transition'
                        >
                            <i className={`fas fa-times online-users-icon ${trayOpen ? 'online-users-icon-showing' : ''}`} />
                        </CSSTransition>
                    </div>
                    {!trayOpen && onlineUsers.length > 0 && <div className='online-users-badge'>{onlineUsers.length}</div>}
                </div>
                <CSSTransition
                    in={trayOpen}
                    timeout={500}
                    classNames='tray-transition'
                >
                    <div className={`online-users-tray ${trayOpen ? 'online-users-tray-showing' : ''}`}>
                        {this.renderOnlineUsers()}
                    </div>
                </CSSTransition>
            </div>
        );
    }

    renderOnlineUsers() {
        const { user, knownUsers, onlineUsers } = this.props;

        return (
            <div className='online-users-inner'>
                <div className='online-users-title'>Users Online ({onlineUsers.length})</div>
                {onlineUsers.length > 0 ?
                    <table className='online-users-table'>
                        <tbody>
                            {onlineUsers.map((userId, index) => {
                                const otherUser = knownUsers[userId];

                                return (
                                    <tr className='online-users-row' key={index}>
                                        <td className='online-users-username'>
                                            <UserDisplay value={`u:${userId}`} knownUsers={knownUsers} />
                                        </td>
                                        {(!user || !user.currentGame) && otherUser.currentGame &&
                                            <td className='online-users-action'>
                                                {this.renderSpectate(otherUser)}
                                            </td>
                                        }
                                        {user && !user.currentGame && !otherUser.currentGame &&
                                            <td className='online-users-action'>
                                                {this.renderChallenge(otherUser)}
                                            </td>
                                        }
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                    :
                    <div className='online-users-empty'>
                        No users online.
                    </div>
                }
            </div>
        );
    }

    renderSpectate(otherUser) {
        return (
            <Tooltip
                title='Spectate'
            >
                <Link
                    to={`/game/${otherUser.currentGame.gameId}`}
                    onClick={() => {
                        amplitude.track('Click Spectate Game', {
                            source: 'online',
                            gameId: otherUser.currentGame.gameId,
                        });

                        this.setState({trayOpen: false});
                    }}
                >
                    <i className='fas fa-eye' />
                </Link>
            </Tooltip>
        );
    }

    renderChallenge(otherUser) {
        return (
            <Tooltip
                arrow={true}
                distance={15}
                trigger='click'
                interactive={false}
                onShow={() => {
                    amplitude.track('Click Challenge', {
                        userId: otherUser.userId,
                    });
                }}
                html={
                    <div className='online-users-challenge-menu'>
                        <div className='online-users-challenge-menu-title'>
                            Challenge
                        </div>
                        <div
                            className='online-users-challenge-menu-item'
                            onClick={() => {
                                amplitude.track('Click Challenge Speed', {
                                    userId: otherUser.userId,
                                    speed: 'standard',
                                });

                                this.setState({trayOpen: false});

                                this.props.createNewGame('standard', false, null, otherUser.username);
                            }}
                        >
                            Standard
                        </div>
                        <div
                            className='online-users-challenge-menu-item'
                            onClick={() => {
                                amplitude.track('Click Challenge Speed', {
                                    userId: otherUser.userId,
                                    speed: 'lightning',
                                });

                                this.setState({trayOpen: false});

                                this.props.createNewGame('lightning', false, null, otherUser.username);
                            }}
                        >
                            Lightning
                        </div>
                    </div>
                }
            >
                <i className='fas fa-crosshairs' />
            </Tooltip>
        );
    }
};
