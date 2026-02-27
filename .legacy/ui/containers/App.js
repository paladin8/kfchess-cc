import * as amplitude from '@amplitude/analytics-browser';
import { Experiment } from '@amplitude/experiment-js-client';
import React, { Component } from 'react';
import { BrowserRouter, Route } from 'react-router-dom';

import About from './About.js';
import Alert from './Alert.js';
import Campaign from './Campaign.js';
import Game from './Game.js';
import Header from './Header.js';
import Home from './Home.js';
import Live from './Live.js';
import PrivacyPolicy from './PrivacyPolicy.js'
import Profile from './Profile.js';
import Replay from './Replay.js';
import Users from './Users.js';
import Listener from '../util/Listener.js';

export default class App extends Component {

    constructor(props) {
        super(props);

        this.state = {
            initialLoadDone: false,
            csrfToken: null,
            user: null,
            knownUsers: {},
            onlineUsers: [],
            playerKeys: null,
            error: null,
            expReady: false,
        };

        this.loadMyInfo = this.loadMyInfo.bind(this);
        this.fetchUserInfo = this.fetchUserInfo.bind(this);
        this.updateUser = this.updateUser.bind(this);
        this.uploadProfilePic = this.uploadProfilePic.bind(this);
        this.createNewGame = this.createNewGame.bind(this);
        this.checkGame = this.checkGame.bind(this);
        this.inviteUser = this.inviteUser.bind(this);
        this.getUserGameHistory = this.getUserGameHistory.bind(this);
        this.getLiveInfo = this.getLiveInfo.bind(this);
        this.startReplay = this.startReplay.bind(this);
        this.fetchCampaignInfo = this.fetchCampaignInfo.bind(this);
        this.startCampaignLevel = this.startCampaignLevel.bind(this);
        this.logout = this.logout.bind(this);

        this.router = null;

        this.experiment = Experiment.initializeWithAmplitudeAnalytics(EXPERIMENT_API_KEY);
    }

    componentDidMount() {
        // hack for development
        // this.setState({
        //     initialLoadDone: true,
        //     knownUsers: {},
        //     onlineUsers: [],
        //     expReady: true,
        // });

        this.loadMyInfo(() => {
            this.setState({ initialLoadDone: true });

            this.listener = new Listener(
                this.state.user ? this.state.user.userId : null,
                () => this.loadMyInfo(),
                data => {
                    const onlineUsers = Object.keys(data.users);

                    this.setState({
                        knownUsers: {
                            ...this.state.knownUsers,
                            ...data.users,
                        },
                        onlineUsers,
                    });
                },
            );
        });
    }

    componentWillUnmount() {
        if (this.listener) {
            this.listener.destroy();
        }
    }

    getRequest(path, callback, errorCallback) {
        fetch(path, {
            credentials: 'same-origin',
            method: 'GET',
        }).then(callback).catch(errorCallback);
    }

    postRequest(path, data, callback, errorCallback) {
        fetch(path, {
            'body': data,
            credentials: 'same-origin',
            headers: {
                'content-type': 'application/json',
                'X-CSRF-Token': this.state.csrfToken,
            },
            method: 'POST',
        }).then(callback).catch(errorCallback);
    }

    loadMyInfo(callback) {
        this.getRequest(
            '/api/user/info',
            response => {
                response.json().then(data => {
                    if (data.loggedIn) {
                        let knownUsers = this.state.knownUsers;
                        knownUsers[data.user.userId] = data.user;

                        this.setState({
                            user: data.user,
                            knownUsers,
                        });

                        amplitude.setUserId(data.user.userId);

                        const identify = new amplitude.Identify();
                        identify.set('username', data.user.username);
                        identify.set('pictureUrl', data.user.pictureUrl);
                        amplitude.identify(identify);

                        if (data.user.currentGame) {
                            const { gameId, playerKey } = data.user.currentGame;
                            this.setState({ playerKeys: null });
                            this.router.history.push(`/game/${gameId}?key=${playerKey}`);
                        }
                    }

                    this.experiment.start().then(() => {
                        this.setState({
                            expReady: true,
                        });
                    }).catch(() => {
                        this.setState({
                            expReady: true,
                        });
                    });

                    this.setState({
                        csrfToken: data.csrfToken,
                    });

                    if (callback) {
                        callback();
                    }
                });
            },
            () => this.setError('Error logging in.')
        );
    }

    fetchUserInfo(userIds, callback) {
        const { knownUsers } = this.state;

        userIds = userIds.filter(userId => !(userId in knownUsers));
        if (userIds.length === 0) {
            callback();
            return;
        }

        const path = '/api/user/info?' + userIds.map(userId => 'userId=' + encodeURIComponent(userId)).join('&');
        this.getRequest(
            path,
            response => {
                response.json().then(data => {
                    this.setState({
                        knownUsers: {
                            ...this.state.knownUsers,
                            ...data.users,
                        },
                    }, () => {
                        callback();
                    });
                });
            },
            () => {
                this.setError('Error fetching user information.');
                callback();
            }
        );
    }

    updateUser(username, callback) {
        amplitude.track('Update User', {
            username,
        });

        this.postRequest(
            '/api/user/update',
            JSON.stringify({ username }),
            response => {
                response.json().then(data => {
                    if (data.success) {
                        let knownUsers = this.state.knownUsers;
                        knownUsers[data.user.userId] = data.user;

                        this.setState({
                            user: data.user,
                            knownUsers,
                        });
                    } else {
                        this.setError(data.message);
                    }
                    callback();
                });
            },
            () => {
                this.setError('Error updating user information.');
                callback()
            }
        );
    }

    uploadProfilePic(data, callback) {
        amplitude.track('Upload Profile Pic');

        if (data.length > 1024 * 64) {
            this.setError('File is too large (max size 64KB).');
            callback();

            return;
        }

        this.postRequest(
            '/api/user/uploadPic',
            data,
            response => {
                response.json().then(data => {
                    if (data.success) {
                        let knownUsers = this.state.knownUsers;
                        knownUsers[data.user.userId] = data.user;

                        this.setState({
                            user: data.user,
                            knownUsers,
                        });
                    } else {
                        this.setError(data.message);
                    }
                    callback();
                });
            },
            () => callback()
        );
    }

    createNewGame(speed, isBot, difficulty, username) {
        amplitude.track('Create New Game', {
            speed,
            isBot,
            difficulty,
        });

        this.postRequest(
            '/api/game/new',
            JSON.stringify({
                speed,
                bots: isBot ? { 2: difficulty } : {},
                username,
            }),
            response => {
                response.json().then(data => {
                    if (data.success) {
                        this.setState({ playerKeys: data.playerKeys });
                        this.router.history.push(`/game/${data.gameId}?key=${data.playerKeys['1']}`);
                    } else {
                        this.setError(data.message);
                    }
                });
            },
            () => this.setError('Error creating new game.')
        );
    }

    checkGame(gameId) {
        this.getRequest(
            `/api/game/check?gameId=${gameId}`,
            response => {
                response.json().then(data => {
                    if (!data.success) {
                        // game did not exist, update user and go to home page
                        this.setState({
                            user: data.user,
                        });

                        this.router.history.push('/');
                    }
                });
            },
            () => this.setError('Error checking game.')
        );
    }

    inviteUser(gameId, username, callback) {
        amplitude.track('Invite User', {
            gameId,
            username,
        });

        this.postRequest(
            '/api/game/invite',
            JSON.stringify({ gameId, player: 2, username }),
            response => {
                response.json().then(data => {
                    if (data.success) {
                        callback();
                    } else {
                        this.setError(data.message);
                    }
                });
            },
            () => this.setError('Error inviting user.')
        );
    }

    getUserGameHistory(userId, offset, count, callback) {
        this.getRequest(
            `/api/user/history?userId=${userId}&offset=${offset}&count=${count}`,
            response => {
                response.json().then(data => {
                    this.setState({
                        knownUsers: {
                            ...this.state.knownUsers,
                            ...data.users,
                        },
                    }, () => {
                        callback(data.history);
                    });
                });
            },
            () => this.setError('Error fetching user game history.')
        );
    }

    getLiveInfo(callback) {
        this.getRequest(
            '/api/live',
            response => {
                response.json().then(data => {
                    this.setState({
                        knownUsers: {
                            ...this.state.knownUsers,
                            ...data.users,
                        },
                    }, () => {
                        callback(data);
                    });
                });
            },
            () => {
                this.setError('Error fetching live info.');
                callback();
            }
        );
    }

    startReplay(historyId, callback) {
        this.postRequest(
            '/api/game/startreplay',
            JSON.stringify({ historyId }),
            response => {
                response.json().then(data => {
                    if (data.success) {
                        callback(data);
                    } else {
                        this.setError(data.message);
                    }
                });
            },
            () => this.setError('Error starting replay.')
        );
    }

    fetchCampaignInfo(userId, callback) {
        this.getRequest(
            `/api/user/campaign?userId=${userId}`,
            response => {
                response.json().then(data => {
                    callback(data);
                });
            },
            () => this.setError('Error fetching campaign info.')
        );
    }

    startCampaignLevel(level) {
        this.postRequest(
            '/api/game/startcampaign',
            JSON.stringify({ level }),
            response => {
                response.json().then(data => {
                    if (data.success) {
                        this.router.history.push(`/game/${data.gameId}?key=${data.playerKeys['1']}`);
                    } else {
                        this.setError(data.message);
                    }
                });
            },
            () => this.setError('Error starting campaign level.')
        );
    }

    logout() {
        this.postRequest(
            '/logout',
            '',
            response => {
                response.json().then(() => {
                    this.router.history.push('/');
                    window.location.reload();
                });
            },
            () => this.setError('Error logging out.')
        );
    }

    setError(message) {
        // add a random id to the error so alert knows when it updated
        this.setState({
            error: { message, id: Math.random() },
        });
    }

    render() {
        const {
            initialLoadDone,
            csrfToken,
            user,
            knownUsers,
            onlineUsers,
            playerKeys,
            error,
            expReady,
        } = this.state;

        return (
            <BrowserRouter ref={router => this.router = router}>
                {initialLoadDone && expReady ? <div>
                    <Header
                        user={user}
                        router={this.router}
                        loadMyInfo={this.loadMyInfo}
                        logout={this.logout}
                    />
                    <Alert error={error} />
                    <Users
                        user={user}
                        knownUsers={knownUsers}
                        onlineUsers={onlineUsers}
                        onOpen={() => {
                            this.loadMyInfo();
                            this.listener.ping();
                        }}
                        createNewGame={this.createNewGame}
                    />
                    <Route exact path='/' render={props => {
                        return (
                            <Home
                                createNewGame={this.createNewGame}
                                expReady={expReady}
                                experiment={this.experiment}
                                {...props}
                            />
                        );
                    }} />
                    <Route path='/live' render={props => {
                        return (
                            <Live
                                user={user}
                                knownUsers={knownUsers}
                                getLiveInfo={this.getLiveInfo}
                            />
                        );
                    }} />
                    <Route path='/about' component={About} />
                    <Route path='/privacy-policy' component={PrivacyPolicy} />
                    <Route path='/profile/:userId' render={props => {
                        return (
                            <Profile
                                user={user}
                                knownUsers={knownUsers}
                                fetchUserInfo={this.fetchUserInfo}
                                fetchCampaignInfo={this.fetchCampaignInfo}
                                updateUser={this.updateUser}
                                uploadProfilePic={this.uploadProfilePic}
                                getUserGameHistory={this.getUserGameHistory}
                                {...props}
                            />
                        );
                    }} />
                    <Route path='/game/:gameId' render={props => {
                        return (
                            <Game
                                user={user}
                                checkGame={this.checkGame}
                                knownUsers={knownUsers}
                                fetchUserInfo={this.fetchUserInfo}
                                inviteUser={this.inviteUser}
                                playerKeys={playerKeys}
                                startCampaignLevel={this.startCampaignLevel}
                                {...props}
                            />
                        )
                    }} />
                    <Route path='/replay/:historyId' render={props => {
                        return (
                            <Replay
                                knownUsers={knownUsers}
                                fetchUserInfo={this.fetchUserInfo}
                                startReplay={this.startReplay}
                                {...props}
                            />
                        )
                    }} />
                    <Route path='/campaign' render={props => {
                        return (
                            <Campaign
                                user={user}
                                fetchCampaignInfo={this.fetchCampaignInfo}
                                startCampaignLevel={this.startCampaignLevel}
                            />
                        );
                    }} />
                </div>
                :
                null
            }
            </BrowserRouter>
        );
    }
};
